import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from achats.models import CommandeAchat, LigneAchat
from fournisseurs.models import Fournisseur
from medicaments.forms import MedicamentForm
from medicaments.models import Categorie, Medicament
from stock.models import LotStock

MEDIA_TEST = tempfile.mkdtemp()


def image(format_="PNG", taille=(20, 20), nom="photo", rembourrage=0):
    tampon = BytesIO()
    Image.new("RGB", taille, "green").save(tampon, format=format_)
    contenu = tampon.getvalue() + b"0" * rembourrage
    extension = {"PNG": "png", "JPEG": "jpg", "GIF": "gif"}[format_]
    return SimpleUploadedFile(f"{nom}.{extension}", contenu)


def donnees_medicament(categorie, **extra):
    donnees = {
        "nom_commercial": "Doliprane",
        "denomination_generique": "Paracétamol",
        "categorie": categorie.pk,
        "forme": "comprime",
        "dosage": "500 mg",
        "laboratoire": "Labo",
        "code_barres": "999",
        "prix_achat": "300",
        "prix_vente": "500",
        "seuil_alerte": "10",
        "statut": "actif",
    }
    donnees.update(extra)
    return donnees


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class CatalogueTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def setUp(self):
        self.categorie = Categorie.objects.create(nom="Antalgiques")
        self.autre_categorie = Categorie.objects.create(nom="Vitamines")

    def med(self, nom="Paracétamol", **kwargs):
        donnees = {"categorie": self.categorie, "prix_achat": 300, "prix_vente": 500}
        donnees.update(kwargs)
        return Medicament.objects.create(nom_commercial=nom, **donnees)


class FormulaireMedicamentTests(CatalogueTestCase):
    def formulaire(self, fichier=None, **extra):
        fichiers = {"photo": fichier} if fichier else None
        return MedicamentForm(donnees_medicament(self.categorie, **extra), fichiers)

    def test_formulaire_valide_avec_photo(self):
        self.assertTrue(self.formulaire(image()).is_valid())

    def test_photo_facultative(self):
        self.assertTrue(self.formulaire().is_valid())

    def test_photo_format_refuse(self):
        form = self.formulaire(image("GIF"))
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_photo_trop_lourde_refusee(self):
        form = self.formulaire(image(rembourrage=2 * 1024 * 1024 + 10))
        self.assertFalse(form.is_valid())
        self.assertIn("lourde", form.errors["photo"][0])

    def test_fichier_non_image_refuse(self):
        faux = SimpleUploadedFile("faux.png", b"ce n'est pas une image")
        form = self.formulaire(faux)
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_prix_negatif_refuse(self):
        self.assertFalse(self.formulaire(prix_vente="-5").is_valid())

    def test_code_barres_duplique_refuse(self):
        self.med(code_barres="999")
        form = self.formulaire(code_barres="999")
        self.assertFalse(form.is_valid())
        self.assertIn("code_barres", form.errors)

    def test_code_barres_vide_accepte_plusieurs_fois(self):
        for nom in ("A", "B"):
            form = MedicamentForm(donnees_medicament(self.categorie, nom_commercial=nom, code_barres=""))
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        self.assertEqual(Medicament.objects.filter(code_barres__isnull=True).count(), 2)


class ListeMedicamentsTests(CatalogueTestCase):
    def ids(self, reponse):
        return [m.nom_commercial for m in reponse.context["page"]]

    def test_liste_affichee(self):
        self.med("Paracétamol")
        r = self.client.get(reverse("medicaments:liste"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Paracétamol")

    def test_recherche_par_nom(self):
        self.med("Paracétamol")
        self.med("Ibuprofène")
        r = self.client.get(reverse("medicaments:liste"), {"q": "ibu"})
        self.assertEqual(self.ids(r), ["Ibuprofène"])

    def test_recherche_par_code_barres(self):
        self.med("Paracétamol", code_barres="12345")
        self.med("Ibuprofène", code_barres="67890")
        r = self.client.get(reverse("medicaments:liste"), {"q": "67890"})
        self.assertEqual(self.ids(r), ["Ibuprofène"])

    def test_filtre_par_categorie(self):
        self.med("Paracétamol")
        self.med("Vitamine C", categorie=self.autre_categorie)
        r = self.client.get(reverse("medicaments:liste"), {"categorie": self.autre_categorie.pk})
        self.assertEqual(self.ids(r), ["Vitamine C"])

    def test_filtre_categorie_invalide_ignore(self):
        self.med("Paracétamol")
        r = self.client.get(reverse("medicaments:liste"), {"categorie": "abc"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.ids(r), ["Paracétamol"])

    def test_tri_par_prix(self):
        self.med("Cher", prix_vente=900)
        self.med("Pas cher", prix_vente=100)
        croissant = self.client.get(reverse("medicaments:liste"), {"tri": "prix"})
        decroissant = self.client.get(reverse("medicaments:liste"), {"tri": "-prix"})
        self.assertEqual(self.ids(croissant), ["Pas cher", "Cher"])
        self.assertEqual(self.ids(decroissant), ["Cher", "Pas cher"])

    def test_tri_inconnu_ignore(self):
        self.med("A")
        r = self.client.get(reverse("medicaments:liste"), {"tri": "n'importe quoi"})
        self.assertEqual(r.status_code, 200)

    def test_pagination(self):
        for i in range(25):
            self.med(f"Med {i:02d}")
        page1 = self.client.get(reverse("medicaments:liste"))
        page3 = self.client.get(reverse("medicaments:liste"), {"page": 3})
        self.assertEqual(len(page1.context["page"]), 10)
        self.assertEqual(len(page3.context["page"]), 5)

    def test_archives_masques_par_defaut(self):
        self.med("Actif")
        self.med("Ancien", statut=Medicament.Statut.ARCHIVE)
        defaut = self.client.get(reverse("medicaments:liste"))
        archives = self.client.get(reverse("medicaments:liste"), {"statut": "archive"})
        tous = self.client.get(reverse("medicaments:liste"), {"statut": "tous"})
        self.assertEqual(self.ids(defaut), ["Actif"])
        self.assertEqual(self.ids(archives), ["Ancien"])
        self.assertEqual(len(self.ids(tous)), 2)

    def test_stock_disponible_exclut_lots_perimes_et_bloques(self):
        m = self.med("Paracétamol")
        demain = timezone.localdate() + timedelta(days=30)
        hier = timezone.localdate() - timedelta(days=1)
        for numero, date, bloque, qte in [("OK", demain, False, 10), ("PER", hier, False, 7),
                                          ("BLO", demain, True, 5)]:
            LotStock.objects.create(medicament=m, numero_lot=numero, date_peremption=date,
                                    quantite_recue=qte, quantite_restante=qte, bloque=bloque)
        r = self.client.get(reverse("medicaments:liste"))
        self.assertEqual(r.context["page"][0].stock_disponible, 10)


class CrudMedicamentTests(CatalogueTestCase):
    def test_ajouter_avec_photo(self):
        donnees = donnees_medicament(self.categorie)
        donnees["photo"] = image()
        r = self.client.post(reverse("medicaments:creer"), donnees)
        medicament = Medicament.objects.get(nom_commercial="Doliprane")
        self.assertRedirects(r, reverse("medicaments:detail", args=[medicament.pk]))
        self.assertTrue(medicament.photo.name.startswith("medicaments/"))
        detail = self.client.get(reverse("medicaments:detail", args=[medicament.pk]))
        self.assertContains(detail, medicament.photo.url)

    def test_ajout_invalide_reaffiche_le_formulaire(self):
        r = self.client.post(reverse("medicaments:creer"), donnees_medicament(self.categorie, prix_vente="-1"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Medicament.objects.count(), 0)

    def test_modifier(self):
        m = self.med("Paracétamol")
        donnees = donnees_medicament(self.categorie, nom_commercial="Paracétamol Forte", prix_vente="650")
        r = self.client.post(reverse("medicaments:modifier", args=[m.pk]), donnees)
        self.assertRedirects(r, reverse("medicaments:detail", args=[m.pk]))
        m.refresh_from_db()
        self.assertEqual(m.nom_commercial, "Paracétamol Forte")
        self.assertEqual(m.prix_vente, Decimal("650"))

    def test_page_confirmation_avant_suppression(self):
        m = self.med()
        r = self.client.get(reverse("medicaments:supprimer", args=[m.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Medicament.objects.filter(pk=m.pk).exists())  # rien supprimé sur un GET

    def test_suppression_sans_historique(self):
        m = self.med()
        r = self.client.post(reverse("medicaments:supprimer", args=[m.pk]))
        self.assertRedirects(r, reverse("medicaments:liste"))
        self.assertFalse(Medicament.objects.filter(pk=m.pk).exists())

    def test_archivage_si_lot(self):
        m = self.med()
        LotStock.objects.create(medicament=m, numero_lot="L", date_peremption=timezone.localdate(),
                                quantite_recue=5, quantite_restante=5)
        self.client.post(reverse("medicaments:supprimer", args=[m.pk]))
        m.refresh_from_db()
        self.assertEqual(m.statut, Medicament.Statut.ARCHIVE)

    def test_archivage_si_achat(self):
        m = self.med()
        user = get_user_model().objects.create_user("u", password="x")
        commande = CommandeAchat.objects.create(
            fournisseur=Fournisseur.objects.create(nom="F"), cree_par=user)
        LigneAchat.objects.create(commande=commande, medicament=m, quantite=1, prix_achat=1)
        self.client.post(reverse("medicaments:supprimer", args=[m.pk]))
        m.refresh_from_db()
        self.assertEqual(m.statut, Medicament.Statut.ARCHIVE)

    def test_medicament_inexistant(self):
        self.assertEqual(self.client.get(reverse("medicaments:detail", args=[999])).status_code, 404)


class CategoriesTests(CatalogueTestCase):
    def test_ajouter(self):
        r = self.client.post(reverse("medicaments:categorie_creer"),
                             {"nom": "Antiseptiques", "description": "Désinfection"})
        self.assertRedirects(r, reverse("medicaments:categories"))
        self.assertTrue(Categorie.objects.filter(nom="Antiseptiques").exists())

    def test_nom_unique(self):
        r = self.client.post(reverse("medicaments:categorie_creer"), {"nom": "Antalgiques"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Categorie.objects.filter(nom="Antalgiques").count(), 1)

    def test_modifier(self):
        self.client.post(reverse("medicaments:categorie_modifier", args=[self.categorie.pk]),
                         {"nom": "Antidouleurs", "description": ""})
        self.categorie.refresh_from_db()
        self.assertEqual(self.categorie.nom, "Antidouleurs")

    def test_recherche(self):
        r = self.client.get(reverse("medicaments:categories"), {"q": "vita"})
        self.assertEqual([c.nom for c in r.context["page"]], ["Vitamines"])

    def test_suppression_categorie_libre(self):
        self.client.post(reverse("medicaments:categorie_supprimer", args=[self.autre_categorie.pk]))
        self.assertFalse(Categorie.objects.filter(pk=self.autre_categorie.pk).exists())

    def test_suppression_categorie_utilisee_refusee(self):
        self.med()
        r = self.client.post(reverse("medicaments:categorie_supprimer", args=[self.categorie.pk]),
                             follow=True)
        self.assertTrue(Categorie.objects.filter(pk=self.categorie.pk).exists())
        self.assertContains(r, "suppression impossible")
