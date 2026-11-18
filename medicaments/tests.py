from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from medicaments.models import Categorie, Medicament


def creer_medicament(**kwargs):
    categorie = kwargs.pop("categorie", None) or Categorie.objects.get_or_create(nom="Antalgiques")[0]
    donnees = {
        "nom_commercial": "Paracétamol",
        "categorie": categorie,
        "prix_achat": Decimal("300"),
        "prix_vente": Decimal("500"),
    }
    donnees.update(kwargs)
    return Medicament.objects.create(**donnees)


class MedicamentModeleTests(TestCase):
    def test_identifiant_automatique_et_unique(self):  # RG01
        a, b = creer_medicament(), creer_medicament(nom_commercial="Ibuprofène")
        self.assertIsNotNone(a.pk)
        self.assertNotEqual(a.pk, b.pk)

    def test_code_barres_duplique_refuse(self):  # RG02
        creer_medicament(code_barres="123456")
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_medicament(nom_commercial="Autre", code_barres="123456")

    def test_code_barres_duplique_refuse_par_validation(self):  # RG02
        creer_medicament(code_barres="123456")
        autre = Medicament(
            nom_commercial="Autre",
            categorie=Categorie.objects.first(),
            prix_achat=1,
            prix_vente=2,
            code_barres="123456",
        )
        with self.assertRaises(ValidationError):
            autre.full_clean()

    def test_plusieurs_medicaments_sans_code_barres(self):  # RG02
        creer_medicament(code_barres="")
        creer_medicament(nom_commercial="Autre", code_barres="")
        self.assertEqual(Medicament.objects.filter(code_barres__isnull=True).count(), 2)

    def test_prix_negatif_refuse_par_validation(self):  # RG03
        m = Medicament(
            nom_commercial="X",
            categorie=Categorie.objects.create(nom="C"),
            prix_achat=Decimal("-1"),
            prix_vente=Decimal("5"),
        )
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_prix_negatif_refuse_par_la_base(self):  # RG03
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_medicament(prix_vente=Decimal("-5"))

    def test_statut_par_defaut_actif(self):
        self.assertTrue(creer_medicament().est_actif)

    def test_categorie_utilisee_non_supprimable(self):
        m = creer_medicament()
        with self.assertRaises(ProtectedError):
            m.categorie.delete()


class JeuDeDonneesTests(TestCase):
    def test_chargement_et_relance_sans_doublon(self):
        call_command("charger_donnees", stdout=StringIO())
        premier = Medicament.objects.count()
        self.assertGreater(premier, 0)
        call_command("charger_donnees", stdout=StringIO())
        self.assertEqual(Medicament.objects.count(), premier)
