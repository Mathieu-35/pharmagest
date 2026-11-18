from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from medicaments.models import Categorie, Medicament
from stock.models import LotStock
from ventes.models import LigneVente, Paiement, RetourVente, Vente


class VenteModeleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("caisse", password="x")
        categorie = Categorie.objects.create(nom="Antalgiques")
        self.med = Medicament.objects.create(
            nom_commercial="Paracétamol", categorie=categorie,
            prix_achat=300, prix_vente=Decimal("500"))
        self.lot = LotStock.objects.create(
            medicament=self.med, numero_lot="L1",
            date_peremption=timezone.localdate() + timedelta(days=100),
            quantite_recue=50, quantite_restante=50)
        self.vente = Vente.objects.create(vendeur=self.user)
        self.ligne = LigneVente.objects.create(
            vente=self.vente, medicament=self.med, lot=self.lot,
            quantite=3, prix_applique=self.med.prix_vente)

    def test_total_vente(self):
        self.assertEqual(self.vente.total, Decimal("1500"))

    def test_prix_fige_apres_changement_du_prix(self):  # RG12
        self.med.prix_vente = Decimal("900")
        self.med.save()
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.prix_applique, Decimal("500"))
        self.assertEqual(self.vente.total, Decimal("1500"))

    def test_quantite_nulle_refusee(self):  # RG03
        with self.assertRaises(IntegrityError), transaction.atomic():
            LigneVente.objects.create(
                vente=self.vente, medicament=self.med, lot=self.lot,
                quantite=0, prix_applique=500)

    def test_prix_negatif_refuse(self):  # RG03
        with self.assertRaises(IntegrityError), transaction.atomic():
            LigneVente.objects.create(
                vente=self.vente, medicament=self.med, lot=self.lot,
                quantite=1, prix_applique=-1)

    def test_lot_doit_correspondre_au_medicament(self):
        autre = Medicament.objects.create(
            nom_commercial="Autre", categorie=self.med.categorie,
            prix_achat=1, prix_vente=2)
        ligne = LigneVente(vente=self.vente, medicament=autre, lot=self.lot,
                           quantite=1, prix_applique=2)
        with self.assertRaises(ValidationError):
            ligne.clean()

    def test_jeton_unique_contre_la_double_validation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vente.objects.create(vendeur=self.user, jeton=self.vente.jeton)

    def test_vente_sans_client_autorisee(self):
        self.assertIsNone(self.vente.client)

    def test_vente_validee_non_supprimable_avec_lignes_en_paiement(self):  # RG10
        Paiement.objects.create(
            vente=self.vente, mode=Paiement.Mode.ESPECES, montant=1500,
            statut=Paiement.Statut.CONFIRME)
        with self.assertRaises(ProtectedError):
            self.vente.delete()

    def test_seuls_les_paiements_confirmes_comptent(self):
        Paiement.objects.create(
            vente=self.vente, mode=Paiement.Mode.MOBILE_MONEY, montant=1500,
            statut=Paiement.Statut.EN_ATTENTE)
        self.assertEqual(self.vente.total_paye, Decimal("0"))
        Paiement.objects.create(
            vente=self.vente, mode=Paiement.Mode.ESPECES, montant=1000,
            statut=Paiement.Statut.CONFIRME)
        self.assertEqual(self.vente.total_paye, Decimal("1000"))

    def test_paiement_montant_nul_refuse(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Paiement.objects.create(vente=self.vente, mode=Paiement.Mode.ESPECES, montant=0)

    def test_retour_ne_depasse_pas_la_quantite_vendue(self):
        RetourVente.objects.create(
            ligne_vente=self.ligne, quantite=2, motif="Erreur", enregistre_par=self.user)
        trop = RetourVente(
            ligne_vente=self.ligne, quantite=2, motif="Trop", enregistre_par=self.user)
        with self.assertRaises(ValidationError):
            trop.clean()
        ok = RetourVente(
            ligne_vente=self.ligne, quantite=1, motif="Reste", enregistre_par=self.user)
        ok.clean()

    def test_ligne_vendue_non_supprimable_si_retour(self):
        RetourVente.objects.create(
            ligne_vente=self.ligne, quantite=1, motif="Erreur", enregistre_par=self.user)
        with self.assertRaises(ProtectedError):
            self.ligne.delete()
