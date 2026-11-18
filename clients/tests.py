from django.test import TestCase
from django.urls import reverse

from clients.models import Client
from utilisateurs import roles
from utilisateurs.outils_tests import creer_utilisateur


class ClientsTests(TestCase):
    def setUp(self):
        self.caissier = creer_utilisateur("caisse", roles.CAISSIER)
        self.client.force_login(self.caissier)

    def test_ajout_et_modification(self):
        r = self.client.post(reverse("clients:creer"), {"nom": "Alice Test", "telephone": "034 00 000 00", "actif": "on"})
        c = Client.objects.get()
        self.assertRedirects(r, reverse("clients:detail", args=[c.pk]))
        self.client.post(reverse("clients:modifier", args=[c.pk]), {"nom": "Alice Modifiée", "actif": "on"})
        c.refresh_from_db()
        self.assertEqual(c.nom, "Alice Modifiée")

    def test_nom_obligatoire(self):
        r = self.client.post(reverse("clients:creer"), {"nom": ""})
        self.assertEqual((r.status_code, Client.objects.count()), (200, 0))

    def test_recherche_et_statut(self):
        Client.objects.create(nom="Alice", telephone="111")
        Client.objects.create(nom="Bob", telephone="222", actif=False)
        par_nom = self.client.get(reverse("clients:liste"), {"q": "ali"})
        par_tel = self.client.get(reverse("clients:liste"), {"q": "222", "statut": "tous"})
        defaut = self.client.get(reverse("clients:liste"))
        self.assertEqual([c.nom for c in par_nom.context["page"]], ["Alice"])
        self.assertEqual([c.nom for c in par_tel.context["page"]], ["Bob"])
        self.assertEqual([c.nom for c in defaut.context["page"]], ["Alice"])

    def test_desactivation_et_reactivation(self):
        c = Client.objects.create(nom="Alice")
        self.client.post(reverse("clients:activation", args=[c.pk]))
        c.refresh_from_db()
        self.assertFalse(c.actif)
        self.client.post(reverse("clients:activation", args=[c.pk]))
        c.refresh_from_db()
        self.assertTrue(c.actif)

    def test_historique_des_ventes_du_client(self):
        from datetime import timedelta
        from django.utils import timezone
        from medicaments.models import Categorie, Medicament
        from stock.models import LotStock
        from ventes import services
        import uuid
        c = Client.objects.create(nom="Alice")
        med = Medicament.objects.create(
            nom_commercial="Para", categorie=Categorie.objects.create(nom="C"), prix_achat=1, prix_vente=100)
        LotStock.objects.create(medicament=med, numero_lot="L", quantite_recue=10, quantite_restante=10,
                                date_peremption=timezone.localdate() + timedelta(days=50))
        vente, _ = services.valider_vente(self.caissier, [{"medicament_id": med.pk, "quantite": 2, "lot_id": None}],
                                          "especes", uuid.uuid4(), c)
        r = self.client.get(reverse("clients:detail", args=[c.pk]))
        self.assertContains(r, vente.numero)
        self.assertContains(r, "200")

    def test_permissions(self):
        self.client.force_login(creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK))
        self.assertEqual(self.client.get(reverse("clients:liste")).status_code, 403)
        self.client.force_login(creer_utilisateur("pharma", roles.PHARMACIEN))
        self.assertEqual(self.client.get(reverse("clients:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("clients:creer")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("clients:liste")).status_code, 302)
