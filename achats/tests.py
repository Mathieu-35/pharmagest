from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from achats.models import CommandeAchat, LigneAchat
from fournisseurs.models import Fournisseur
from medicaments.models import Categorie, Medicament
from stock.models import LotStock


class CommandeAchatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("stock", password="x")
        self.fournisseur = Fournisseur.objects.create(nom="Grossiste")
        categorie = Categorie.objects.create(nom="Antalgiques")
        self.med1 = Medicament.objects.create(
            nom_commercial="A", categorie=categorie, prix_achat=100, prix_vente=150)
        self.med2 = Medicament.objects.create(
            nom_commercial="B", categorie=categorie, prix_achat=200, prix_vente=300)
        self.commande = CommandeAchat.objects.create(
            fournisseur=self.fournisseur, cree_par=self.user)

    def test_statut_initial_brouillon(self):
        self.assertEqual(self.commande.statut, CommandeAchat.Statut.BROUILLON)

    def test_montant_total_calcule(self):
        LigneAchat.objects.create(
            commande=self.commande, medicament=self.med1, quantite=10, prix_achat=Decimal("100"))
        LigneAchat.objects.create(
            commande=self.commande, medicament=self.med2, quantite=5, prix_achat=Decimal("250.50"))
        self.assertEqual(self.commande.montant_total, Decimal("2252.50"))

    def test_commande_ne_modifie_pas_le_stock(self):  # RG04
        LigneAchat.objects.create(
            commande=self.commande, medicament=self.med1, quantite=10, prix_achat=100)
        self.assertEqual(LotStock.objects.count(), 0)

    def test_quantite_nulle_refusee(self):  # RG03
        with self.assertRaises(IntegrityError), transaction.atomic():
            LigneAchat.objects.create(
                commande=self.commande, medicament=self.med1, quantite=0, prix_achat=100)

    def test_prix_negatif_refuse(self):  # RG03
        with self.assertRaises(IntegrityError), transaction.atomic():
            LigneAchat.objects.create(
                commande=self.commande, medicament=self.med1, quantite=1, prix_achat=-1)

    def test_medicament_unique_par_commande(self):
        LigneAchat.objects.create(
            commande=self.commande, medicament=self.med1, quantite=1, prix_achat=100)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LigneAchat.objects.create(
                commande=self.commande, medicament=self.med1, quantite=2, prix_achat=100)
