import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from config import sauvegarde
from medicaments.models import Categorie, Medicament
from stock.models import LotStock, MouvementStock
from utilisateurs import roles
from utilisateurs.models import JournalAudit
from utilisateurs.outils_tests import creer_utilisateur
from ventes.models import LigneVente, Paiement, Vente
from ventes.outils_tests import CaisseTestCase


class SauvegardeTestCase(CaisseTestCase):
    """Jeu de données réaliste : utilisateurs et rôles, médicament avec photo, lots, vente, mouvements."""

    def setUp(self):
        self.dossier_media = tempfile.mkdtemp()
        self.dossier_sauvegardes = tempfile.mkdtemp()
        self.reglages = override_settings(
            MEDIA_ROOT=self.dossier_media, SAUVEGARDES_DIR=self.dossier_sauvegardes,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
        self.reglages.enable()
        super().setUp()
        self.med.photo.save("para.png", ContentFile(b"\x89PNG-photo-de-test"), save=True)
        self.vente = self.vendre(3, mode="mobile_money")
        self.caissier.set_password("Mot-de-passe-solide-42")
        self.caissier.save()
        self.caissier.refresh_from_db()

    def tearDown(self):
        super().tearDown()
        self.reglages.disable()
        shutil.rmtree(self.dossier_media, ignore_errors=True)
        shutil.rmtree(self.dossier_sauvegardes, ignore_errors=True)

    def photo_path(self):
        return Path(self.dossier_media) / self.med.photo.name

    def etat(self):
        """Résumé comparable de la base."""
        comptes = sauvegarde._compter()
        comptes.pop("sessions.session", None)   # les sessions ne sont pas sauvegardées : tout le monde se reconnecte
        return {
            "comptes": comptes,
            "prix": Medicament.objects.get(pk=self.med.pk).prix_vente,
            "stock": sorted(LotStock.objects.values_list("numero_lot", "quantite_restante")),
            "mdp": get_user_model().objects.get(pk=self.caissier.pk).password,
            "droits_caissier": sorted(Group.objects.get(name=roles.CAISSIER)
                                      .permissions.values_list("codename", flat=True)),
            "role_caissier": sorted(self.caissier.groups.values_list("name", flat=True)),
        }

    def alterer_archive(self, chemin, donnees=None, manifest_modifie=None, media_modifies=None, recalculer=False):
        """Réécrit une archive en modifiant un de ses éléments (pour simuler une altération)."""
        with zipfile.ZipFile(chemin) as archive:
            contenus = {nom: archive.read(nom) for nom in archive.namelist()}
        if donnees is not None:
            contenus["donnees.json"] = donnees
        manifest = json.loads(contenus["manifest.json"])
        if recalculer:
            manifest["donnees_sha256"] = hashlib.sha256(contenus["donnees.json"]).hexdigest()
        if manifest_modifie:
            manifest.update(manifest_modifie)
        contenus["manifest.json"] = json.dumps(manifest).encode()
        for nom, contenu in (media_modifies or {}).items():
            contenus[nom] = contenu
        nouvelle = Path(str(chemin) + ".modifiee.zip")
        with zipfile.ZipFile(nouvelle, "w") as archive:
            for nom, contenu in contenus.items():
                archive.writestr(nom, contenu)
        return nouvelle


class CreationDeSauvegardeTests(SauvegardeTestCase):
    def test_archive_complete_et_verifiee(self):
        chemin, manifest = sauvegarde.creer_sauvegarde()
        self.assertTrue(chemin.is_file())
        self.assertEqual(chemin.parent, Path(self.dossier_sauvegardes))
        with zipfile.ZipFile(chemin) as archive:
            noms = archive.namelist()
        self.assertIn("manifest.json", noms)
        self.assertIn("donnees.json", noms)
        self.assertIn(f"media/{self.med.photo.name}", noms)
        self.assertEqual(manifest["comptes"]["medicaments.medicament"], 1)
        self.assertEqual(manifest["comptes"]["ventes.vente"], 1)
        self.assertGreater(manifest["objets"], 10)
        sauvegarde.verifier_archive(chemin)   # ne lève rien

    def test_contenu_sensible_et_inutile(self):
        _, manifest = sauvegarde.creer_sauvegarde()
        for exclu in ("contenttypes.contenttype", "auth.permission", "sessions.session"):
            self.assertNotIn(exclu, manifest["comptes"])
        for inclus in ("auth.user", "auth.group", "stock.lotstock", "stock.mouvementstock",
                       "ventes.lignevente", "ventes.paiement", "utilisateurs.journalaudit"):
            self.assertIn(inclus, manifest["comptes"])

    def test_deux_sauvegardes_ne_s_ecrasent_pas(self):
        a, _ = sauvegarde.creer_sauvegarde()
        b, _ = sauvegarde.creer_sauvegarde()
        self.assertNotEqual(a, b)
        self.assertTrue(a.is_file() and b.is_file())

    def test_sans_photos(self):
        shutil.rmtree(self.dossier_media)
        chemin, manifest = sauvegarde.creer_sauvegarde()
        self.assertEqual(manifest["media"], [])
        sauvegarde.verifier_archive(chemin)

    def test_commande_sauvegarder(self):
        sortie = io.StringIO()
        call_command("sauvegarder", stdout=sortie)
        self.assertIn("Sauvegarde créée et vérifiée", sortie.getvalue())
        self.assertEqual(len(list(Path(self.dossier_sauvegardes).glob("pharmagest-*.zip"))), 1)


class VerificationTests(SauvegardeTestCase):
    def test_fichier_introuvable(self):
        with self.assertRaises(sauvegarde.ErreurSauvegarde):
            sauvegarde.verifier_archive(Path(self.dossier_sauvegardes) / "inexistant.zip")

    def test_fichier_qui_n_est_pas_une_archive(self):
        faux = Path(self.dossier_sauvegardes) / "faux.zip"
        faux.write_bytes(b"ceci n'est pas un zip")
        with self.assertRaises(sauvegarde.ErreurSauvegarde):
            sauvegarde.verifier_archive(faux)

    def test_donnees_alterees_detectees(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        modifiee = self.alterer_archive(chemin, donnees=b"[]")
        with self.assertRaisesMessage(sauvegarde.ErreurSauvegarde, "altérées"):
            sauvegarde.verifier_archive(modifiee)

    def test_photo_alteree_detectee(self):
        chemin, manifest = sauvegarde.creer_sauvegarde()
        nom = f"media/{manifest['media'][0]['chemin']}"
        modifiee = self.alterer_archive(chemin, media_modifies={nom: b"photo piratee"})
        with self.assertRaisesMessage(sauvegarde.ErreurSauvegarde, "Photo altérée"):
            sauvegarde.verifier_archive(modifiee)

    def test_chemin_de_photo_dangereux_refuse(self):
        chemin, manifest = sauvegarde.creer_sauvegarde()
        media = [dict(manifest["media"][0], chemin="../evil.txt")]
        modifiee = self.alterer_archive(chemin, manifest_modifie={"media": media})
        with self.assertRaisesMessage(sauvegarde.ErreurSauvegarde, "refusé"):
            sauvegarde.verifier_archive(modifiee)

    def test_manifest_absent(self):
        chemin = Path(self.dossier_sauvegardes) / "incomplet.zip"
        with zipfile.ZipFile(chemin, "w") as archive:
            archive.writestr("donnees.json", "[]")
        with self.assertRaises(sauvegarde.ErreurSauvegarde):
            sauvegarde.verifier_archive(chemin)


class RestaurationTests(SauvegardeTestCase):
    def test_restaurer_une_sauvegarde_recupere_les_donnees(self):  # scénario du cahier des charges
        chemin, _ = sauvegarde.creer_sauvegarde()
        avant = self.etat()
        octets_photo = self.photo_path().read_bytes()

        # « Sinistre » : on modifie, ajoute et perd des données
        Medicament.objects.filter(pk=self.med.pk).update(prix_vente=Decimal("1"))
        Medicament.objects.create(nom_commercial="Intrus", categorie=self.med.categorie, prix_achat=1, prix_vente=1)
        LotStock.objects.filter(pk=self.lot_a.pk).update(quantite_restante=0)
        vente2 = self.vendre(2)
        creer_utilisateur("nouveau", roles.CAISSIER)
        self.caissier.set_password("autre-mot-de-passe-91")
        self.caissier.save()
        self.photo_path().unlink()
        Group.objects.get(name=roles.CAISSIER).permissions.clear()

        resume = sauvegarde.restaurer(chemin)

        self.assertEqual(self.etat(), avant)
        self.assertFalse(Medicament.objects.filter(nom_commercial="Intrus").exists())
        self.assertFalse(Vente.objects.filter(pk=vente2.pk).exists())
        self.assertFalse(get_user_model().objects.filter(username="nouveau").exists())
        self.assertEqual(self.photo_path().read_bytes(), octets_photo)
        self.assertEqual((resume["photos"], resume["essai"]), (1, False))
        self.assertTrue(get_user_model().objects.get(pk=self.caissier.pk).check_password("Mot-de-passe-solide-42"))

    def test_donnees_liees_recuperees(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        sauvegarde.restaurer(chemin)
        vente = Vente.objects.get(pk=self.vente.pk)
        self.assertEqual(vente.total, Decimal("1500"))
        self.assertEqual(vente.vendeur.username, "caisse")
        self.assertEqual(vente.paiements.get().statut, Paiement.Statut.EN_ATTENTE)
        self.assertEqual(vente.lignes.get().lot.numero_lot, "A")
        self.assertEqual(MouvementStock.objects.filter(type="sortie").count(), 1)
        self.assertEqual(Medicament.objects.get(pk=self.med.pk).code_barres, "123456")
        self.assertTrue(JournalAudit.objects.filter(action="Vente enregistrée").exists())

    def test_les_droits_des_roles_fonctionnent_apres_restauration(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        sauvegarde.restaurer(chemin)
        self.client.force_login(get_user_model().objects.get(pk=self.caissier.pk))
        from django.urls import reverse
        self.assertEqual(self.client.get(reverse("ventes:caisse")).status_code, 200)
        self.assertEqual(self.client.get(reverse("utilisateurs:liste")).status_code, 403)

    def test_restauration_deux_fois_de_suite(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        avant = self.etat()
        sauvegarde.restaurer(chemin)
        sauvegarde.restaurer(chemin)
        self.assertEqual(self.etat(), avant)

    def test_sauvegarde_de_securite_avant_restauration(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        Medicament.objects.create(nom_commercial="Intrus", categorie=self.med.categorie, prix_achat=1, prix_vente=1)
        resume = sauvegarde.restaurer(chemin)
        securite = Path(resume["sauvegarde_securite"])
        self.assertTrue(securite.name.startswith("avant-restauration-"))
        manifest, _ = sauvegarde.verifier_archive(securite)
        self.assertEqual(manifest["comptes"]["medicaments.medicament"], 2)   # l'état d'avant, avec « Intrus »

    def test_essai_ne_modifie_rien(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        Medicament.objects.filter(pk=self.med.pk).update(prix_vente=Decimal("1"))
        Medicament.objects.create(nom_commercial="Intrus", categorie=self.med.categorie, prix_achat=1, prix_vente=1)
        self.photo_path().unlink()
        modifie = self.etat()
        resume = sauvegarde.restaurer(chemin, essai=True)
        self.assertTrue(resume["essai"])
        self.assertEqual(self.etat(), modifie)                      # données inchangées
        self.assertTrue(Medicament.objects.filter(nom_commercial="Intrus").exists())
        self.assertFalse(self.photo_path().exists())                # photos non restaurées
        self.assertEqual(len(list(Path(self.dossier_sauvegardes).glob("avant-restauration-*"))), 0)

    def test_archive_alteree_refusee_avant_toute_modification(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        Medicament.objects.create(nom_commercial="Intrus", categorie=self.med.categorie, prix_achat=1, prix_vente=1)
        avant = self.etat()
        modifiee = self.alterer_archive(chemin, donnees=b"[]")
        with self.assertRaises(sauvegarde.ErreurSauvegarde):
            sauvegarde.restaurer(modifiee)
        self.assertEqual(self.etat(), avant)
        self.assertTrue(Medicament.objects.filter(nom_commercial="Intrus").exists())

    def test_archive_incoherente_annulee_sans_rien_perdre(self):
        """Données au bon format mais impossibles à charger : la base doit rester intacte."""
        chemin, _ = sauvegarde.creer_sauvegarde()
        with zipfile.ZipFile(chemin) as archive:
            objets = json.loads(archive.read("donnees.json"))
        for objet in objets:
            if objet["model"] == "stock.lotstock":
                objet["fields"]["medicament"] = 99999        # médicament inexistant
        modifiee = self.alterer_archive(
            chemin, donnees=json.dumps(objets).encode(), recalculer=True)
        Medicament.objects.create(nom_commercial="Intrus", categorie=self.med.categorie, prix_achat=1, prix_vente=1)
        avant = self.etat()
        with self.assertRaisesMessage(sauvegarde.ErreurSauvegarde, "aucune donnée n'a été modifiée"):
            sauvegarde.restaurer(modifiee)
        self.assertEqual(self.etat(), avant)
        self.assertTrue(Medicament.objects.filter(nom_commercial="Intrus").exists())

    def test_nombre_d_enregistrements_controle(self):
        chemin, manifest = sauvegarde.creer_sauvegarde()
        faux = dict(manifest["comptes"], **{"medicaments.medicament": 7})
        modifiee = self.alterer_archive(chemin, manifest_modifie={"comptes": faux})
        avant = self.etat()
        with self.assertRaisesMessage(sauvegarde.ErreurSauvegarde, "ne correspond pas"):
            sauvegarde.restaurer(modifiee)
        self.assertEqual(self.etat(), avant)

    def test_restauration_dans_une_base_videe(self):
        """Cas d'un nouveau serveur : base migrée mais sans données."""
        chemin, _ = sauvegarde.creer_sauvegarde()
        avant = self.etat()
        sauvegarde._vider_les_donnees()
        self.assertEqual(Medicament.objects.count(), 0)
        sauvegarde.restaurer(chemin)
        self.assertEqual(self.etat(), avant)


class CommandesTests(SauvegardeTestCase):
    def lancer(self, nom, *args, **options):
        sortie = io.StringIO()
        call_command(nom, *args, stdout=sortie, **options)
        return sortie.getvalue()

    def test_restaurer_exige_une_confirmation(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        with self.assertRaisesMessage(CommandError, "--confirmer"):
            call_command("restaurer", str(chemin))

    def test_commande_essai(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        self.assertIn("Essai réussi", self.lancer("restaurer", str(chemin), essai=True))

    def test_commande_restauration(self):
        chemin, _ = sauvegarde.creer_sauvegarde()
        Medicament.objects.create(nom_commercial="Intrus", categorie=self.med.categorie, prix_achat=1, prix_vente=1)
        sortie = self.lancer("restaurer", str(chemin), confirmer=True)
        self.assertIn("Restauration terminée", sortie)
        self.assertFalse(Medicament.objects.filter(nom_commercial="Intrus").exists())

    def test_commande_archive_invalide(self):
        faux = Path(self.dossier_sauvegardes) / "faux.zip"
        faux.write_bytes(b"xxx")
        with self.assertRaises(CommandError):
            call_command("restaurer", str(faux), confirmer=True)
