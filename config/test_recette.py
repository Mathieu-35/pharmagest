"""Recette : les 11 scénarios du tableau de la section 9 du cahier des charges.

Chaque scénario passe par les pages de l'application (requêtes HTTP) avec le rôle qui
l'effectue réellement, et vérifie le « résultat attendu » du cahier des charges.
Voir docs/RECETTE.md.
"""

import io
import shutil
import tempfile
import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from reportlab import rl_config

from achats.models import CommandeAchat, LigneAchat, ReceptionAchat
from config import sauvegarde
from fournisseurs.models import Fournisseur
from medicaments.models import Categorie, Medicament
from rapports.outils_tests import texte_pdf
from stock.models import LotStock, MouvementStock
from utilisateurs import roles
from utilisateurs.outils_tests import HASH_RAPIDE, creer_utilisateur
from ventes import services
from ventes.models import Vente
from ventes.panier import CLE

DEMAIN_LOIN = timezone.localdate() + timedelta(days=365)


def png(nom="photo.png"):
    tampon = io.BytesIO()
    Image.new("RGB", (40, 40), "green").save(tampon, format="PNG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class RecetteTestCase(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.sauvegardes = tempfile.mkdtemp()
        self.reglages = override_settings(MEDIA_ROOT=self.media, SAUVEGARDES_DIR=self.sauvegardes)
        self.reglages.enable()
        self.pharmacien = creer_utilisateur("pharmacien", roles.PHARMACIEN)
        self.gestionnaire = creer_utilisateur("gestionnaire", roles.GESTIONNAIRE_STOCK)
        self.caissier = creer_utilisateur("caissier", roles.CAISSIER)
        self.categorie = Categorie.objects.create(nom="Antalgiques")
        self.aujourdhui = timezone.localdate()

    def tearDown(self):
        self.reglages.disable()
        shutil.rmtree(self.media, ignore_errors=True)
        shutil.rmtree(self.sauvegardes, ignore_errors=True)

    def connecter(self, utilisateur):
        self.client.force_login(utilisateur)

    def medicament(self, nom="Paracétamol", **kw):
        donnees = {"categorie": self.categorie, "prix_achat": 300, "prix_vente": Decimal("500"),
                   "code_barres": f"CB-{uuid.uuid4().hex[:8]}"}
        donnees.update(kw)
        return Medicament.objects.create(nom_commercial=nom, **donnees)

    def lot(self, medicament, numero="L1", jours=200, quantite=20, bloque=False):
        return LotStock.objects.create(
            medicament=medicament, numero_lot=numero, bloque=bloque,
            date_peremption=self.aujourdhui + timedelta(days=jours),
            quantite_recue=quantite, quantite_restante=quantite)

    def stock(self, medicament):
        return sum(l.quantite_restante for l in LotStock.objects.filter(medicament=medicament))

    def formulaire_medicament(self, **extra):
        donnees = {"nom_commercial": "Doliprane", "denomination_generique": "Paracétamol",
                   "categorie": self.categorie.pk, "forme": "comprime", "dosage": "500 mg",
                   "laboratoire": "Labo", "code_barres": "3400000000011", "prix_achat": "300",
                   "prix_vente": "500", "seuil_alerte": "10", "statut": "actif"}
        donnees.update(extra)
        return donnees


class Scenario01a03_Medicaments(RecetteTestCase):
    def test_01_ajouter_un_medicament_avec_photo(self):
        """Résultat attendu : médicament enregistré et photo affichée."""
        self.connecter(self.pharmacien)
        donnees = self.formulaire_medicament(photo=png())
        r = self.client.post(reverse("medicaments:creer"), donnees)
        medicament = Medicament.objects.get(nom_commercial="Doliprane")
        self.assertRedirects(r, reverse("medicaments:detail", args=[medicament.pk]))
        self.assertTrue((Path(self.media) / medicament.photo.name).is_file())
        page = self.client.get(reverse("medicaments:detail", args=[medicament.pk]))
        self.assertContains(page, f'src="{medicament.photo.url}"')
        liste = self.client.get(reverse("medicaments:liste"))
        self.assertContains(liste, medicament.photo.url)

    def test_02_modifier_un_medicament(self):
        """Résultat attendu : informations mises à jour."""
        self.connecter(self.pharmacien)
        m = self.medicament("Ancien nom")
        self.client.post(reverse("medicaments:modifier", args=[m.pk]), self.formulaire_medicament(
            nom_commercial="Nouveau nom", prix_vente="750", dosage="1 g", code_barres="NOUVEAU-1"))
        page = self.client.get(reverse("medicaments:detail", args=[m.pk]))
        self.assertContains(page, "Nouveau nom")
        self.assertContains(page, "1 g")
        m.refresh_from_db()
        self.assertEqual((m.nom_commercial, m.prix_vente), ("Nouveau nom", Decimal("750")))

    def test_03_supprimer_ou_archiver_un_medicament(self):
        """Résultat attendu : historique protégé."""
        self.connecter(self.pharmacien)
        avec_historique = self.medicament("Avec historique")
        lot = self.lot(avec_historique)
        MouvementStock.objects.create(lot=lot, type="entree", quantite=20, motif="Réception")
        sans_historique = self.medicament("Sans historique")

        self.client.post(reverse("medicaments:supprimer", args=[avec_historique.pk]))
        avec_historique.refresh_from_db()
        self.assertEqual(avec_historique.statut, Medicament.Statut.ARCHIVE)          # archivé, pas supprimé
        self.assertEqual(LotStock.objects.filter(medicament=avec_historique).count(), 1)
        self.assertEqual(MouvementStock.objects.filter(lot=lot).count(), 1)           # historique intact

        self.client.post(reverse("medicaments:supprimer", args=[sans_historique.pk]))
        self.assertFalse(Medicament.objects.filter(pk=sans_historique.pk).exists())   # supprimé


class Scenario04_Reception(RecetteTestCase):
    def test_04_receptionner_un_achat_de_20_unites(self):
        """Résultat attendu : stock augmenté de 20 une seule fois."""
        med = self.medicament()
        fournisseur = Fournisseur.objects.create(nom="Grossiste")
        self.connecter(self.gestionnaire)
        # Commande en brouillon puis validée : le stock ne bouge pas
        self.client.post(reverse("achats:creer"), {
            "fournisseur": fournisseur.pk, "lignes-TOTAL_FORMS": "1", "lignes-INITIAL_FORMS": "0",
            "lignes-MIN_NUM_FORMS": "0", "lignes-MAX_NUM_FORMS": "1000",
            "lignes-0-medicament": med.pk, "lignes-0-quantite": "20", "lignes-0-prix_achat": "300"})
        commande = CommandeAchat.objects.get()
        self.client.post(reverse("achats:valider", args=[commande.pk]))
        self.assertEqual(self.stock(med), 0)

        ligne = LigneAchat.objects.get(commande=commande)
        jeton = str(uuid.uuid4())
        donnees = {"jeton": jeton, f"quantite_{ligne.pk}": "20", f"lot_{ligne.pk}": "LOT-1",
                   f"peremption_{ligne.pk}": DEMAIN_LOIN.isoformat()}
        self.client.post(reverse("achats:reception", args=[commande.pk]), donnees)
        self.assertEqual(self.stock(med), 20)
        self.client.post(reverse("achats:reception", args=[commande.pk]), donnees)   # double envoi
        self.assertEqual(self.stock(med), 20)
        self.assertEqual(ReceptionAchat.objects.count(), 1)
        self.assertEqual(MouvementStock.objects.filter(type="entree").count(), 1)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.RECEPTIONNEE)


class Scenario05a07_Ventes(RecetteTestCase):
    def setUp(self):
        super().setUp()
        self.med = self.medicament()
        self.lot_a = self.lot(self.med, "A", jours=60, quantite=10)
        self.connecter(self.caissier)

    def ajouter_au_panier(self, quantite, lot=""):
        return self.client.post(reverse("ventes:panier_ajouter"), {
            "medicament": self.med.pk, "quantite": quantite, "lot": lot}, follow=True)

    def valider(self, **extra):
        donnees = {"jeton": self.client.session[CLE]["jeton"], "mode": "especes", "client": ""}
        donnees.update(extra)
        return self.client.post(reverse("ventes:valider"), donnees, follow=True)

    def test_05_vendre_3_unites(self):
        """Résultat attendu : stock diminué de 3 une seule fois."""
        self.ajouter_au_panier(3)
        jeton = self.client.session[CLE]["jeton"]
        self.valider()
        self.assertEqual(self.stock(self.med), 7)
        self.client.post(reverse("ventes:valider"), {"jeton": jeton, "mode": "especes", "client": ""})  # double envoi
        self.assertEqual(self.stock(self.med), 7)
        self.assertEqual(Vente.objects.count(), 1)
        self.assertEqual(MouvementStock.objects.filter(type="sortie").count(), 1)
        self.assertEqual(Vente.objects.get().vendeur, self.caissier)

    def test_06_vendre_plus_que_le_stock_disponible(self):
        """Résultat attendu : vente refusée."""
        r = self.ajouter_au_panier(11)
        self.assertContains(r, "Stock insuffisant")
        self.assertEqual(self.client.session.get(CLE, {}).get("lignes", []), [])
        with self.assertRaises(services.ErreurVente):                       # même en forçant la validation
            services.valider_vente(self.caissier, [{"medicament_id": self.med.pk, "quantite": 11, "lot_id": None}],
                                   "especes", uuid.uuid4())
        self.assertEqual((Vente.objects.count(), self.stock(self.med)), (0, 10))

    def test_07_vendre_un_lot_perime(self):
        """Résultat attendu : vente refusée."""
        perime = self.lot(self.med, "PERIME", jours=-1, quantite=50)
        r = self.ajouter_au_panier(1, lot=perime.pk)
        self.assertContains(r, "pas vendable")
        with self.assertRaises(services.ErreurVente):
            services.valider_vente(self.caissier, [{"medicament_id": self.med.pk, "quantite": 1, "lot_id": perime.pk}],
                                   "especes", uuid.uuid4())
        # En automatique, le lot périmé n'est jamais utilisé : seuls les 10 du lot valide sont vendables
        with self.assertRaises(services.ErreurVente):
            services.valider_vente(self.caissier, [{"medicament_id": self.med.pk, "quantite": 11, "lot_id": None}],
                                   "especes", uuid.uuid4())
        perime.refresh_from_db()
        self.assertEqual((Vente.objects.count(), perime.quantite_restante), (0, 50))


class Scenario08_Permissions(RecetteTestCase):
    def test_08_tenter_un_acces_sans_permission(self):
        """Résultat attendu : accès interdit."""
        m = self.medicament()
        self.connecter(self.caissier)
        for url in (reverse("medicaments:creer"), reverse("medicaments:modifier", args=[m.pk]),
                    reverse("achats:liste"), reverse("fournisseurs:liste"), reverse("utilisateurs:liste"),
                    reverse("stock:inventaire"), reverse("rapports:stock")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse("medicaments:supprimer", args=[m.pk])).status_code, 403)
        self.assertTrue(Medicament.objects.filter(pk=m.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(reverse("medicaments:liste")).status_code, 302)   # non connecté


class Scenario09_RecuPdf(RecetteTestCase):
    def setUp(self):
        super().setUp()
        self._compression = rl_config.pageCompression
        rl_config.pageCompression = 0     # PDF non compressé pour relire son texte

    def tearDown(self):
        rl_config.pageCompression = self._compression
        super().tearDown()

    def test_09_generer_un_recu_pdf(self):
        """Résultat attendu : document lisible avec les bons totaux."""
        med = self.medicament(prix_vente=Decimal("1250"))
        self.lot(med, quantite=20)
        self.connecter(self.caissier)
        vente, _ = services.valider_vente(
            self.caissier, [{"medicament_id": med.pk, "quantite": 3, "lot_id": None}], "especes", uuid.uuid4())
        reponse = self.client.get(reverse("rapports:recu", args=[vente.pk]))
        self.assertEqual((reponse.status_code, reponse["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(reponse.content.startswith(b"%PDF"))
        texte = texte_pdf(reponse.content)
        for attendu in (vente.numero, "Paracétamol", "3", "1 250,00 Ar", "3 750,00 Ar", "Reçu de vente"):
            self.assertIn(attendu, texte)


class Scenario11_Restauration(RecetteTestCase):
    def test_11_restaurer_une_sauvegarde(self):
        """Résultat attendu : données récupérées correctement."""
        med = self.medicament()
        med.photo.save("p.png", png(), save=True)
        self.lot(med, quantite=20)
        vente, _ = services.valider_vente(
            self.caissier, [{"medicament_id": med.pk, "quantite": 4, "lot_id": None}], "especes", uuid.uuid4())
        archive, _ = sauvegarde.creer_sauvegarde()
        etat = (Medicament.objects.count(), Vente.objects.count(), self.stock(med), vente.total,
                get_user_model().objects.count())
        photo = Path(self.media) / med.photo.name
        contenu_photo = photo.read_bytes()

        # Perte de données : suppression de la photo, modification du stock et des prix, ajout parasite
        photo.unlink()
        Medicament.objects.filter(pk=med.pk).update(prix_vente=Decimal("1"))
        LotStock.objects.update(quantite_restante=0)
        self.medicament("Intrus")
        creer_utilisateur("intrus")

        resume = sauvegarde.restaurer(archive)
        self.assertEqual((Medicament.objects.count(), Vente.objects.count(), self.stock(med),
                          Vente.objects.get().total, get_user_model().objects.count()), etat)
        self.assertEqual(Medicament.objects.get(pk=med.pk).prix_vente, Decimal("500"))
        self.assertEqual(photo.read_bytes(), contenu_photo)
        self.assertEqual(resume["photos"], 1)


class Scenario10_ValidationsSimultanees(TransactionTestCase):
    """Deux validations de vente exactement en même temps sur le même stock."""

    def test_10_deux_validations_simultanees(self):
        """Résultat attendu : aucune sortie de stock en double ni stock négatif."""
        utilisateur = get_user_model().objects.create(username="caisse")
        medicament = Medicament.objects.create(
            nom_commercial="Para", categorie=Categorie.objects.create(nom="C"), prix_achat=1, prix_vente=500)
        lot = LotStock.objects.create(
            medicament=medicament, numero_lot="L", quantite_recue=10, quantite_restante=10,
            date_peremption=timezone.localdate() + timedelta(days=100))
        ligne = [{"medicament_id": medicament.pk, "quantite": 6, "lot_id": None}]

        def lancer(jetons):
            barriere, resultats = threading.Barrier(len(jetons)), []

            def tache(jeton):
                try:
                    barriere.wait()
                    vente, creee = services.valider_vente(utilisateur, ligne, "especes", jeton)
                    resultats.append("creee" if creee else "deja-faite")
                except services.ErreurVente:
                    resultats.append("refusee")
                finally:
                    connection.close()

            fils = [threading.Thread(target=tache, args=(j,)) for j in jetons]
            [f.start() for f in fils]
            [f.join() for f in fils]
            return resultats

        # Deux clients différents veulent chacun 6 unités sur un stock de 10
        resultats = lancer([uuid.uuid4(), uuid.uuid4()])
        lot.refresh_from_db()
        self.assertEqual(resultats.count("creee"), 1, resultats)
        self.assertEqual(Vente.objects.count(), 1)
        self.assertEqual(lot.quantite_restante, 4)
        self.assertEqual(MouvementStock.objects.filter(type="sortie").count(), 1)

        # Le même formulaire envoyé deux fois en même temps
        LotStock.objects.filter(pk=lot.pk).update(quantite_restante=10)
        avant = Vente.objects.count()
        jeton = uuid.uuid4()
        resultats = lancer([jeton, jeton])
        lot.refresh_from_db()
        self.assertEqual(Vente.objects.count() - avant, 1, resultats)
        self.assertEqual(lot.quantite_restante, 4)
        self.assertGreaterEqual(lot.quantite_restante, 0)
