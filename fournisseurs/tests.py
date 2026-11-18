from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from achats.models import CommandeAchat, LigneAchat
from fournisseurs.models import Fournisseur
from medicaments.models import Categorie, Medicament
from utilisateurs import roles
from utilisateurs.outils_tests import creer_utilisateur


class FournisseurTestCase(TestCase):
    def setUp(self):
        self.gestionnaire = creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK)
        self.client.force_login(self.gestionnaire)

    def donnees(self, **extra):
        d = {"nom": "Grossiste Test", "adresse": "Lot 1", "telephone": "020 11 111 11",
             "email": "g@example.com", "numero_fiscal": "NIF1", "contact_principal": "M. Test",
             "actif": "on"}
        d.update(extra)
        return d


class FournisseurCrudTests(FournisseurTestCase):
    def test_creation(self):
        r = self.client.post(reverse("fournisseurs:creer"), self.donnees())
        f = Fournisseur.objects.get(nom="Grossiste Test")
        self.assertRedirects(r, reverse("fournisseurs:detail", args=[f.pk]))
        self.assertTrue(f.actif)

    def test_nom_obligatoire(self):
        r = self.client.post(reverse("fournisseurs:creer"), self.donnees(nom=""))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Fournisseur.objects.count(), 0)

    def test_email_invalide_refuse(self):
        r = self.client.post(reverse("fournisseurs:creer"), self.donnees(email="pas-un-email"))
        self.assertEqual(r.status_code, 200)

    def test_modification(self):
        f = Fournisseur.objects.create(nom="Ancien")
        self.client.post(reverse("fournisseurs:modifier", args=[f.pk]), self.donnees(nom="Nouveau"))
        f.refresh_from_db()
        self.assertEqual(f.nom, "Nouveau")

    def test_recherche_par_nom_et_telephone(self):
        Fournisseur.objects.create(nom="Alpha Pharma", telephone="111")
        Fournisseur.objects.create(nom="Beta Distrib", telephone="222")
        par_nom = self.client.get(reverse("fournisseurs:liste"), {"q": "alpha"})
        par_tel = self.client.get(reverse("fournisseurs:liste"), {"q": "222"})
        self.assertEqual([f.nom for f in par_nom.context["page"]], ["Alpha Pharma"])
        self.assertEqual([f.nom for f in par_tel.context["page"]], ["Beta Distrib"])

    def test_inactifs_masques_par_defaut(self):
        Fournisseur.objects.create(nom="Actif")
        Fournisseur.objects.create(nom="Inactif", actif=False)
        defaut = self.client.get(reverse("fournisseurs:liste"))
        inactifs = self.client.get(reverse("fournisseurs:liste"), {"statut": "inactif"})
        tous = self.client.get(reverse("fournisseurs:liste"), {"statut": "tous"})
        self.assertEqual([f.nom for f in defaut.context["page"]], ["Actif"])
        self.assertEqual([f.nom for f in inactifs.context["page"]], ["Inactif"])
        self.assertEqual(len(tous.context["page"]), 2)

    def test_desactivation_et_reactivation(self):
        f = Fournisseur.objects.create(nom="F")
        self.client.post(reverse("fournisseurs:activation", args=[f.pk]))
        f.refresh_from_db()
        self.assertFalse(f.actif)
        self.client.post(reverse("fournisseurs:activation", args=[f.pk]))
        f.refresh_from_db()
        self.assertTrue(f.actif)

    def test_activation_exige_post(self):
        f = Fournisseur.objects.create(nom="F")
        self.assertEqual(self.client.get(reverse("fournisseurs:activation", args=[f.pk])).status_code, 405)


class FournisseurHistoriqueTests(FournisseurTestCase):
    def setUp(self):
        super().setUp()
        self.f = Fournisseur.objects.create(nom="Grossiste")
        categorie = Categorie.objects.create(nom="Antalgiques")
        self.med = Medicament.objects.create(
            nom_commercial="Para", categorie=categorie, prix_achat=100, prix_vente=150)
        self.commande = CommandeAchat.objects.create(fournisseur=self.f, cree_par=self.gestionnaire)
        LigneAchat.objects.create(commande=self.commande, medicament=self.med, quantite=10, prix_achat=Decimal("100"))

    def test_historique_des_achats_et_montants(self):
        r = self.client.get(reverse("fournisseurs:detail", args=[self.f.pk]))
        self.assertContains(r, self.commande.numero)
        self.assertContains(r, "1000")  # 10 × 100

    def test_desactiver_conserve_les_anciennes_operations(self):
        self.client.post(reverse("fournisseurs:activation", args=[self.f.pk]))
        self.assertTrue(CommandeAchat.objects.filter(pk=self.commande.pk).exists())

    def test_suppression_refusee_si_commandes(self):
        r = self.client.post(reverse("fournisseurs:supprimer", args=[self.f.pk]))
        self.assertEqual(r.status_code, 403)  # le gestionnaire n'a pas le droit de supprimer
        admin = creer_utilisateur("chef", roles.ADMINISTRATEUR)
        self.client.force_login(admin)
        self.client.post(reverse("fournisseurs:supprimer", args=[self.f.pk]))
        self.assertTrue(Fournisseur.objects.filter(pk=self.f.pk).exists())

    def test_suppression_possible_sans_commande(self):
        libre = Fournisseur.objects.create(nom="Libre")
        self.client.force_login(creer_utilisateur("chef", roles.ADMINISTRATEUR))
        self.client.post(reverse("fournisseurs:supprimer", args=[libre.pk]))
        self.assertFalse(Fournisseur.objects.filter(pk=libre.pk).exists())


class FournisseurPermissionsTests(FournisseurTestCase):
    def test_visiteur_anonyme(self):
        self.client.logout()
        r = self.client.get(reverse("fournisseurs:liste"))
        self.assertEqual(r.status_code, 302)

    def test_caissier_interdit(self):
        self.client.force_login(creer_utilisateur("caisse", roles.CAISSIER))
        self.assertEqual(self.client.get(reverse("fournisseurs:liste")).status_code, 403)
        self.assertEqual(self.client.get(reverse("fournisseurs:creer")).status_code, 403)

    def test_pharmacien_consulte_sans_modifier(self):
        f = Fournisseur.objects.create(nom="F")
        self.client.force_login(creer_utilisateur("pharma", roles.PHARMACIEN))
        self.assertEqual(self.client.get(reverse("fournisseurs:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("fournisseurs:creer")).status_code, 403)
        self.assertEqual(self.client.post(reverse("fournisseurs:activation", args=[f.pk])).status_code, 403)

    def test_gestionnaire_ne_supprime_pas(self):
        f = Fournisseur.objects.create(nom="F")
        self.assertEqual(self.client.get(reverse("fournisseurs:supprimer", args=[f.pk])).status_code, 403)
