"""Aides communes aux tests des ventes."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from medicaments.models import Categorie, Medicament
from stock.models import LotStock
from utilisateurs import roles
from utilisateurs.outils_tests import creer_utilisateur
from ventes import services


class CaisseTestCase(TestCase):
    """Un caissier connecté, un médicament à 500 avec deux lots (A périme avant B)."""

    def setUp(self):
        self.caissier = creer_utilisateur("caisse", roles.CAISSIER)
        self.client.force_login(self.caissier)
        self.aujourdhui = timezone.localdate()
        categorie = Categorie.objects.create(nom="Antalgiques")
        self.med = Medicament.objects.create(
            nom_commercial="Paracétamol", categorie=categorie, code_barres="123456",
            prix_achat=300, prix_vente=Decimal("500"))
        self.lot_a = self.creer_lot(self.med, "A", jours=30, quantite=10)
        self.lot_b = self.creer_lot(self.med, "B", jours=90, quantite=10)

    def creer_lot(self, medicament, numero, jours=100, quantite=10, bloque=False):
        return LotStock.objects.create(
            medicament=medicament, numero_lot=numero,
            date_peremption=self.aujourdhui + timedelta(days=jours),
            quantite_recue=quantite, quantite_restante=quantite, bloque=bloque)

    def autre_medicament(self, nom="Ibuprofène", prix="700", **kw):
        return Medicament.objects.create(
            nom_commercial=nom, categorie=self.med.categorie, prix_achat=1,
            prix_vente=Decimal(prix), **kw)

    def stock(self, medicament=None):
        medicament = medicament or self.med
        return sum(l.quantite_restante for l in LotStock.objects.filter(medicament=medicament))

    def vendre(self, quantite=3, mode="especes", medicament=None, lot_id=None, client=None, jeton=None):
        vente, _ = services.valider_vente(
            self.caissier,
            [{"medicament_id": (medicament or self.med).pk, "quantite": quantite, "lot_id": lot_id}],
            mode, jeton or uuid.uuid4(), client)
        return vente
