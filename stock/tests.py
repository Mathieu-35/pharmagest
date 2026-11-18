from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from medicaments.models import Categorie, Medicament
from stock.models import LotStock


def creer_lot(medicament=None, numero="L1", jours=100, recue=20, restante=20, **kw):
    if medicament is None:
        categorie = Categorie.objects.get_or_create(nom="Antalgiques")[0]
        medicament = Medicament.objects.create(
            nom_commercial="Paracétamol", categorie=categorie, prix_achat=300, prix_vente=500
        )
    return LotStock.objects.create(
        medicament=medicament,
        numero_lot=numero,
        date_peremption=timezone.localdate() + timedelta(days=jours),
        quantite_recue=recue,
        quantite_restante=restante,
        **kw,
    )


class LotStockTests(TestCase):
    def test_lot_valide_est_vendable(self):  # RG08
        self.assertTrue(creer_lot().est_vendable)

    def test_lot_perime_non_vendable(self):  # RG08
        lot = creer_lot(jours=-1)
        self.assertTrue(lot.est_perime)
        self.assertFalse(lot.est_vendable)

    def test_lot_bloque_non_vendable(self):  # RG08
        self.assertFalse(creer_lot(bloque=True).est_vendable)

    def test_lot_vide_non_vendable(self):
        self.assertFalse(creer_lot(restante=0).est_vendable)

    def test_quantite_negative_refusee_par_la_base(self):  # RG07
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_lot(restante=-1)

    def test_restante_superieure_a_recue_refusee(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_lot(recue=10, restante=11)
        lot = LotStock(medicament=Medicament.objects.create(
            nom_commercial="Y", categorie=Categorie.objects.create(nom="C"),
            prix_achat=1, prix_vente=2), numero_lot="Z",
            date_peremption=timezone.localdate(), quantite_recue=5, quantite_restante=6)
        with self.assertRaises(ValidationError):
            lot.clean()

    def test_numero_de_lot_unique_par_medicament(self):
        lot = creer_lot(numero="A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_lot(medicament=lot.medicament, numero="A")

    def test_ordre_fefo(self):
        lointain = creer_lot(numero="B", jours=300)
        proche = creer_lot(medicament=lointain.medicament, numero="A", jours=30)
        self.assertEqual(list(LotStock.objects.all()), [proche, lointain])
