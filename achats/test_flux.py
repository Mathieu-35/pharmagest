import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from achats import services
from achats.models import CommandeAchat, LigneAchat, LigneReception, ReceptionAchat
from fournisseurs.models import Fournisseur
from medicaments.models import Categorie, Medicament
from stock.models import LotStock, MouvementStock
from utilisateurs import roles
from utilisateurs.models import JournalAudit
from utilisateurs.outils_tests import creer_utilisateur

PEREMPTION = (timezone.localdate() + timedelta(days=365)).isoformat()


def stock_total(medicament):
    return sum(l.quantite_restante for l in LotStock.objects.filter(medicament=medicament))


class AchatsTestCase(TestCase):
    def setUp(self):
        self.user = creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK)
        self.client.force_login(self.user)
        self.fournisseur = Fournisseur.objects.create(nom="Grossiste")
        categorie = Categorie.objects.create(nom="Antalgiques")
        self.med1 = Medicament.objects.create(
            nom_commercial="Para", categorie=categorie, prix_achat=100, prix_vente=150)
        self.med2 = Medicament.objects.create(
            nom_commercial="Ibu", categorie=categorie, prix_achat=200, prix_vente=300)

    # --- aides ---
    def donnees_commande(self, lignes, fournisseur=None, extra=5):
        d = {
            "fournisseur": (fournisseur or self.fournisseur).pk,
            "lignes-TOTAL_FORMS": str(max(extra, len(lignes))),
            "lignes-INITIAL_FORMS": "0", "lignes-MIN_NUM_FORMS": "0", "lignes-MAX_NUM_FORMS": "1000",
        }
        for i in range(max(extra, len(lignes))):
            medicament, quantite, prix = lignes[i] if i < len(lignes) else ("", "", "")
            d[f"lignes-{i}-medicament"] = medicament.pk if medicament else ""
            d[f"lignes-{i}-quantite"] = quantite
            d[f"lignes-{i}-prix_achat"] = prix
        return d

    def creer_commande(self, statut=CommandeAchat.Statut.COMMANDEE, lignes=None):
        commande = CommandeAchat.objects.create(
            fournisseur=self.fournisseur, cree_par=self.user, statut=statut)
        for medicament, quantite, prix in (lignes or [(self.med1, 20, Decimal("100"))]):
            LigneAchat.objects.create(commande=commande, medicament=medicament, quantite=quantite, prix_achat=prix)
        return commande

    def donnees_reception(self, commande, quantites, jeton=None, lot="LOT-A", peremption=PEREMPTION):
        d = {"jeton": str(jeton or uuid.uuid4())}
        for ligne in commande.lignes.all():
            q = quantites.get(ligne.pk, quantites.get(ligne.medicament_id, 0))
            d[f"quantite_{ligne.pk}"] = q
            d[f"lot_{ligne.pk}"] = lot if q else ""
            d[f"peremption_{ligne.pk}"] = peremption if q else ""
        return d

    def receptionner(self, commande, quantites, **kw):
        return self.client.post(
            reverse("achats:reception", args=[commande.pk]),
            self.donnees_reception(commande, quantites, **kw), follow=True)


class CreationCommandeTests(AchatsTestCase):
    def test_creation_en_brouillon_avec_total_calcule(self):
        r = self.client.post(reverse("achats:creer"), self.donnees_commande(
            [(self.med1, 10, "100"), (self.med2, 5, "250.50")]))
        commande = CommandeAchat.objects.get()
        self.assertRedirects(r, reverse("achats:detail", args=[commande.pk]))
        self.assertEqual(commande.statut, CommandeAchat.Statut.BROUILLON)
        self.assertEqual(commande.cree_par, self.user)
        self.assertEqual(commande.lignes.count(), 2)
        self.assertEqual(commande.montant_total, Decimal("2252.50"))

    def test_la_commande_ne_modifie_pas_le_stock(self):  # RG04
        self.client.post(reverse("achats:creer"), self.donnees_commande([(self.med1, 10, "100")]))
        self.assertEqual(LotStock.objects.count(), 0)
        self.assertEqual(MouvementStock.objects.count(), 0)

    def test_commande_vide_refusee(self):
        r = self.client.post(reverse("achats:creer"), self.donnees_commande([]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CommandeAchat.objects.count(), 0)

    def test_medicament_en_double_refuse(self):
        r = self.client.post(reverse("achats:creer"), self.donnees_commande(
            [(self.med1, 1, "100"), (self.med1, 2, "100")]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CommandeAchat.objects.count(), 0)

    def test_quantite_nulle_et_prix_negatif_refuses(self):
        for ligne in [(self.med1, 0, "100"), (self.med1, 1, "-5")]:
            r = self.client.post(reverse("achats:creer"), self.donnees_commande([ligne]))
            self.assertEqual(r.status_code, 200)
        self.assertEqual(CommandeAchat.objects.count(), 0)

    def test_fournisseur_inactif_non_propose(self):
        inactif = Fournisseur.objects.create(nom="Inactif", actif=False)
        r = self.client.post(reverse("achats:creer"), self.donnees_commande(
            [(self.med1, 1, "100")], fournisseur=inactif))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CommandeAchat.objects.count(), 0)

    def test_medicament_archive_non_propose(self):
        self.med1.statut = Medicament.Statut.ARCHIVE
        self.med1.save()
        r = self.client.post(reverse("achats:creer"), self.donnees_commande([(self.med1, 1, "100")]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CommandeAchat.objects.count(), 0)

    def test_creation_journalisee(self):
        self.client.post(reverse("achats:creer"), self.donnees_commande([(self.med1, 1, "100")]))
        self.assertTrue(JournalAudit.objects.filter(action="Commande créée", utilisateur=self.user).exists())


class ModificationEtStatutsTests(AchatsTestCase):
    def test_modification_d_un_brouillon(self):
        commande = self.creer_commande(CommandeAchat.Statut.BROUILLON)
        ligne = commande.lignes.get()
        d = {
            "fournisseur": self.fournisseur.pk,
            "lignes-TOTAL_FORMS": "4", "lignes-INITIAL_FORMS": "1",
            "lignes-MIN_NUM_FORMS": "0", "lignes-MAX_NUM_FORMS": "1000",
            "lignes-0-id": ligne.pk, "lignes-0-commande": commande.pk,
            "lignes-0-medicament": self.med1.pk, "lignes-0-quantite": "30", "lignes-0-prix_achat": "110",
        }
        for i in (1, 2, 3):
            d.update({f"lignes-{i}-medicament": "", f"lignes-{i}-quantite": "", f"lignes-{i}-prix_achat": ""})
        r = self.client.post(reverse("achats:modifier", args=[commande.pk]), d)
        self.assertRedirects(r, reverse("achats:detail", args=[commande.pk]))
        ligne.refresh_from_db()
        self.assertEqual((ligne.quantite, ligne.prix_achat), (30, Decimal("110")))

    def test_commande_validee_non_modifiable(self):
        commande = self.creer_commande(CommandeAchat.Statut.COMMANDEE)
        r = self.client.get(reverse("achats:modifier", args=[commande.pk]), follow=True)
        self.assertRedirects(r, reverse("achats:detail", args=[commande.pk]))
        self.assertContains(r, "brouillon")

    def test_validation(self):
        commande = self.creer_commande(CommandeAchat.Statut.BROUILLON)
        page = self.client.get(reverse("achats:valider", args=[commande.pk]))
        self.assertEqual(page.status_code, 200)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.BROUILLON)  # GET = confirmation seulement
        self.client.post(reverse("achats:valider", args=[commande.pk]))
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.COMMANDEE)
        self.assertEqual(LotStock.objects.count(), 0)  # toujours aucun stock (RG04)

    def test_double_validation_sans_effet(self):
        commande = self.creer_commande(CommandeAchat.Statut.BROUILLON)
        self.client.post(reverse("achats:valider", args=[commande.pk]))
        r = self.client.post(reverse("achats:valider", args=[commande.pk]), follow=True)
        self.assertContains(r, "brouillon")
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.COMMANDEE)

    def test_annulation(self):
        for statut in (CommandeAchat.Statut.BROUILLON, CommandeAchat.Statut.COMMANDEE):
            commande = self.creer_commande(statut)
            self.client.post(reverse("achats:annuler", args=[commande.pk]))
            commande.refresh_from_db()
            self.assertEqual(commande.statut, CommandeAchat.Statut.ANNULEE)

    def test_commande_partiellement_receptionnee_non_annulable(self):
        commande = self.creer_commande()
        self.receptionner(commande, {self.med1.pk: 5})
        self.client.post(reverse("achats:annuler", args=[commande.pk]))
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.PARTIELLE)


class ReceptionTests(AchatsTestCase):
    def test_reception_de_20_unites_augmente_le_stock_une_seule_fois(self):  # RG05
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        jeton = uuid.uuid4()
        self.receptionner(commande, {self.med1.pk: 20}, jeton=jeton)
        self.assertEqual(stock_total(self.med1), 20)
        # Le même formulaire envoyé une seconde fois n'ajoute rien
        r = self.receptionner(commande, {self.med1.pk: 20}, jeton=jeton)
        self.assertEqual(stock_total(self.med1), 20)
        self.assertEqual(ReceptionAchat.objects.count(), 1)
        self.assertContains(r, "déjà été enregistrée")

    def test_lot_mouvement_et_statut_apres_reception(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        self.receptionner(commande, {self.med1.pk: 20}, lot="LOT-X")
        lot = LotStock.objects.get()
        self.assertEqual((lot.numero_lot, lot.quantite_recue, lot.quantite_restante), ("LOT-X", 20, 20))
        mouvement = MouvementStock.objects.get()
        self.assertEqual((mouvement.type, mouvement.quantite, mouvement.utilisateur),
                         (MouvementStock.Type.ENTREE, 20, self.user))
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.RECEPTIONNEE)
        self.assertEqual(LigneReception.objects.get().lot, lot)

    def test_reception_partielle_puis_complete(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        self.receptionner(commande, {self.med1.pk: 8}, lot="L1")
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.PARTIELLE)
        self.assertEqual(stock_total(self.med1), 8)
        self.receptionner(commande, {self.med1.pk: 12}, lot="L2")
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.RECEPTIONNEE)
        self.assertEqual(stock_total(self.med1), 20)
        self.assertEqual(commande.montant_receptionne, Decimal("2000"))

    def test_reception_au_dela_de_la_commande_refusee(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        r = self.receptionner(commande, {self.med1.pk: 21})
        self.assertContains(r, "Maximum 20")
        self.assertEqual(stock_total(self.med1), 0)
        self.assertEqual(ReceptionAchat.objects.count(), 0)

    def test_reception_de_plusieurs_lignes(self):
        commande = self.creer_commande(lignes=[(self.med1, 10, Decimal("100")), (self.med2, 4, Decimal("200"))])
        self.receptionner(commande, {self.med1.pk: 10, self.med2.pk: 4})
        self.assertEqual((stock_total(self.med1), stock_total(self.med2)), (10, 4))

    def test_commande_non_validee_non_receptionnable(self):
        for statut in (CommandeAchat.Statut.BROUILLON, CommandeAchat.Statut.ANNULEE, CommandeAchat.Statut.RECEPTIONNEE):
            commande = self.creer_commande(statut)
            r = self.client.get(reverse("achats:reception", args=[commande.pk]))
            self.assertEqual(r.status_code, 302)
            self.receptionner(commande, {self.med1.pk: 1})
        self.assertEqual(LotStock.objects.count(), 0)

    def test_meme_lot_meme_date_cumule_les_quantites(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        self.receptionner(commande, {self.med1.pk: 5}, lot="L1")
        self.receptionner(commande, {self.med1.pk: 7}, lot="L1")
        lot = LotStock.objects.get()
        self.assertEqual((lot.quantite_recue, lot.quantite_restante), (12, 12))

    def test_meme_lot_autre_date_refuse_sans_rien_modifier(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        self.receptionner(commande, {self.med1.pk: 5}, lot="L1")
        autre_date = (timezone.localdate() + timedelta(days=500)).isoformat()
        r = self.receptionner(commande, {self.med1.pk: 5}, lot="L1", peremption=autre_date)
        self.assertContains(r, "autre date de péremption")
        self.assertEqual(stock_total(self.med1), 5)
        self.assertEqual(ReceptionAchat.objects.count(), 1)

    def test_champs_de_lot_obligatoires(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        ligne = commande.lignes.get()
        r = self.client.post(reverse("achats:reception", args=[commande.pk]), {
            "jeton": str(uuid.uuid4()), f"quantite_{ligne.pk}": 5,
            f"lot_{ligne.pk}": "", f"peremption_{ligne.pk}": ""})
        self.assertContains(r, "numéro de lot")
        self.assertContains(r, "date de péremption")
        self.assertEqual(stock_total(self.med1), 0)

    def test_lot_deja_perime_refuse(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        hier = (timezone.localdate() - timedelta(days=1)).isoformat()
        r = self.receptionner(commande, {self.med1.pk: 5}, peremption=hier)
        self.assertContains(r, "déjà périmé")
        self.assertEqual(stock_total(self.med1), 0)

    def test_aucune_quantite_refusee(self):
        commande = self.creer_commande()
        r = self.receptionner(commande, {})
        self.assertContains(r, "au moins une quantité")
        self.assertEqual(ReceptionAchat.objects.count(), 0)

    def test_jeton_manquant_refuse(self):
        commande = self.creer_commande()
        d = self.donnees_reception(commande, {self.med1.pk: 5})
        d.pop("jeton")
        self.client.post(reverse("achats:reception", args=[commande.pk]), d)
        self.assertEqual(stock_total(self.med1), 0)

    def test_reception_journalisee(self):
        commande = self.creer_commande()
        self.receptionner(commande, {self.med1.pk: 5})
        self.assertTrue(JournalAudit.objects.filter(action="Réception enregistrée", utilisateur=self.user).exists())


class ServiceReceptionAtomiciteTests(AchatsTestCase):
    def test_erreur_sur_une_ligne_annule_toute_la_reception(self):
        commande = self.creer_commande(lignes=[(self.med1, 10, Decimal("100")), (self.med2, 4, Decimal("200"))])
        l1, l2 = commande.lignes.order_by("pk")
        saisies = [
            {"ligne_id": l1.pk, "quantite": 10, "numero_lot": "A", "date_peremption": timezone.localdate() + timedelta(days=100)},
            {"ligne_id": l2.pk, "quantite": 99, "numero_lot": "B", "date_peremption": timezone.localdate() + timedelta(days=100)},
        ]
        with self.assertRaises(services.ErreurAchat):
            services.receptionner(commande.pk, self.user, uuid.uuid4(), saisies)
        self.assertEqual(LotStock.objects.count(), 0)
        self.assertEqual(MouvementStock.objects.count(), 0)
        self.assertEqual(ReceptionAchat.objects.count(), 0)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, CommandeAchat.Statut.COMMANDEE)

    def test_rejeu_du_meme_jeton_au_niveau_service(self):
        commande = self.creer_commande(lignes=[(self.med1, 20, Decimal("100"))])
        ligne = commande.lignes.get()
        saisies = [{"ligne_id": ligne.pk, "quantite": 5, "numero_lot": "A",
                    "date_peremption": timezone.localdate() + timedelta(days=100)}]
        jeton = uuid.uuid4()
        r1, creee1 = services.receptionner(commande.pk, self.user, jeton, saisies)
        r2, creee2 = services.receptionner(commande.pk, self.user, jeton, saisies)
        self.assertEqual((creee1, creee2, r1.pk), (True, False, r2.pk))
        self.assertEqual(stock_total(self.med1), 5)

    def test_ligne_d_une_autre_commande_refusee(self):
        commande = self.creer_commande()
        autre = self.creer_commande()
        ligne_autre = autre.lignes.get()
        with self.assertRaises(services.ErreurAchat):
            services.receptionner(commande.pk, self.user, uuid.uuid4(), [
                {"ligne_id": ligne_autre.pk, "quantite": 1, "numero_lot": "A",
                 "date_peremption": timezone.localdate() + timedelta(days=10)}])
        self.assertEqual(LotStock.objects.count(), 0)


class PermissionsAchatsTests(AchatsTestCase):
    def test_caissier_interdit(self):
        commande = self.creer_commande()
        self.client.force_login(creer_utilisateur("caisse", roles.CAISSIER))
        for url in [reverse("achats:liste"), reverse("achats:creer"), reverse("achats:detail", args=[commande.pk]),
                    reverse("achats:reception", args=[commande.pk])]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_pharmacien_consulte_sans_agir(self):
        commande = self.creer_commande()
        self.client.force_login(creer_utilisateur("pharma", roles.PHARMACIEN))
        self.assertEqual(self.client.get(reverse("achats:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("achats:detail", args=[commande.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("achats:creer")).status_code, 403)
        self.assertEqual(self.client.get(reverse("achats:reception", args=[commande.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("achats:annuler", args=[commande.pk])).status_code, 403)

    def test_visiteur_anonyme(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("achats:liste")).status_code, 302)

    def test_recherche_et_filtre_de_la_liste(self):
        self.creer_commande(CommandeAchat.Statut.BROUILLON)
        autre = Fournisseur.objects.create(nom="Autre Labo")
        CommandeAchat.objects.create(fournisseur=autre, cree_par=self.user, statut=CommandeAchat.Statut.COMMANDEE)
        par_nom = self.client.get(reverse("achats:liste"), {"q": "autre"})
        par_statut = self.client.get(reverse("achats:liste"), {"statut": "brouillon"})
        self.assertEqual(len(par_nom.context["page"]), 1)
        self.assertEqual(len(par_statut.context["page"]), 1)
