from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from medicaments.models import Categorie, Medicament
from stock import services
from stock.models import LotStock, MouvementStock
from utilisateurs import roles
from utilisateurs.models import JournalAudit
from utilisateurs.outils_tests import creer_utilisateur


class StockTestCase(TestCase):
    def setUp(self):
        self.user = creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK)
        self.client.force_login(self.user)
        self.categorie = Categorie.objects.create(nom="Antalgiques")
        self.aujourdhui = timezone.localdate()

    def med(self, nom="Para", seuil=10, **kw):
        return Medicament.objects.create(
            nom_commercial=nom, categorie=self.categorie, prix_achat=1, prix_vente=2,
            seuil_alerte=seuil, **kw)

    def lot(self, medicament, numero="L1", jours=200, quantite=20, restante=None, bloque=False):
        return LotStock.objects.create(
            medicament=medicament, numero_lot=numero,
            date_peremption=self.aujourdhui + timedelta(days=jours),
            quantite_recue=quantite,
            quantite_restante=quantite if restante is None else restante, bloque=bloque)

    def noms(self, reponse):
        return [m.nom_commercial for m in reponse.context["page"]]


class StockDisponibleTests(StockTestCase):
    def test_stock_disponible_exclut_perimes_et_bloques(self):
        m = self.med()
        self.lot(m, "OK", jours=100, quantite=10)
        self.lot(m, "PER", jours=-1, quantite=7)
        self.lot(m, "BLO", jours=100, quantite=5, bloque=True)
        r = self.client.get(reverse("stock:disponible"))
        ligne = r.context["page"][0]
        self.assertEqual((ligne.stock_disponible, ligne.stock_non_vendable), (10, 12))

    def test_rupture_de_stock(self):
        vide, plein = self.med("Vide"), self.med("Plein")
        self.lot(plein, quantite=50)
        self.lot(vide, "P", jours=-5, quantite=3)  # seul lot périmé = rupture
        r = self.client.get(reverse("stock:disponible"), {"etat": "rupture"})
        self.assertEqual(self.noms(r), ["Vide"])

    def test_medicament_sans_lot_en_rupture(self):
        self.med("Sans lot")
        r = self.client.get(reverse("stock:disponible"), {"etat": "rupture"})
        self.assertEqual(self.noms(r), ["Sans lot"])

    def test_stock_sous_le_seuil(self):
        bas, egal, haut = self.med("Bas", seuil=10), self.med("Egal", seuil=10), self.med("Haut", seuil=10)
        self.lot(bas, quantite=9)
        self.lot(egal, quantite=10)   # égal au seuil : pas inférieur
        self.lot(haut, quantite=30)
        r = self.client.get(reverse("stock:disponible"), {"etat": "faible"})
        self.assertEqual(self.noms(r), ["Bas"])

    def test_medicaments_archives_masques(self):
        self.med("Actif")
        self.med("Archive", statut=Medicament.Statut.ARCHIVE)
        r = self.client.get(reverse("stock:disponible"))
        self.assertEqual(self.noms(r), ["Actif"])

    def test_recherche(self):
        self.med("Paracétamol", code_barres="111")
        self.med("Ibuprofène", code_barres="222")
        self.assertEqual(self.noms(self.client.get(reverse("stock:disponible"), {"q": "222"})), ["Ibuprofène"])

    def test_alerte_visuelle_affichee(self):
        self.med("Vide")
        self.assertContains(self.client.get(reverse("stock:disponible")), "Rupture")


class LotsEtPeremptionsTests(StockTestCase):
    def setUp(self):
        super().setUp()
        m = self.med()
        self.normal = self.lot(m, "NORMAL", jours=200)
        self.proche = self.lot(m, "PROCHE", jours=10)
        self.perime = self.lot(m, "PERIME", jours=-3)
        self.bloque = self.lot(m, "BLOQUE", jours=200, bloque=True)
        self.epuise = self.lot(m, "EPUISE", jours=200, quantite=5, restante=0)

    def numeros(self, etat=None, **extra):
        params = {"etat": etat} if etat else {}
        params.update(extra)
        r = self.client.get(reverse("stock:lots"), params)
        return {l.numero_lot for l in r.context["page"]}

    def test_par_defaut_lots_en_stock(self):
        self.assertEqual(self.numeros(), {"NORMAL", "PROCHE", "PERIME", "BLOQUE"})

    def test_produits_proches_de_la_peremption(self):
        self.assertEqual(self.numeros("proches"), {"PROCHE"})

    def test_produits_perimes(self):
        self.assertEqual(self.numeros("perimes"), {"PERIME"})

    def test_lots_bloques_et_epuises(self):
        self.assertEqual(self.numeros("bloques"), {"BLOQUE"})
        self.assertEqual(self.numeros("epuises"), {"EPUISE"})
        self.assertEqual(len(self.numeros("tous")), 5)

    def test_etat_inconnu_ignore(self):
        self.assertEqual(self.numeros("n'importe quoi"), {"NORMAL", "PROCHE", "PERIME", "BLOQUE"})

    def test_recherche_par_numero_de_lot(self):
        self.assertEqual(self.numeros("tous", q="proch"), {"PROCHE"})

    def test_ordre_fefo_dans_la_liste(self):
        r = self.client.get(reverse("stock:lots"))
        dates = [l.date_peremption for l in r.context["page"]]
        self.assertEqual(dates, sorted(dates))

    def test_seuil_de_proximite_configurable(self):
        with self.settings(JOURS_ALERTE_PEREMPTION=300):
            self.assertEqual(self.numeros("proches"), {"NORMAL", "PROCHE", "BLOQUE"})


class BlocageDeLotTests(StockTestCase):
    def test_blocage_et_deblocage(self):
        m = self.med()
        lot = self.lot(m, quantite=10)
        self.client.post(reverse("stock:blocage", args=[lot.pk]))
        lot.refresh_from_db()
        self.assertTrue(lot.bloque)
        self.assertFalse(lot.est_vendable)
        r = self.client.get(reverse("stock:disponible"))
        self.assertEqual(r.context["page"][0].stock_disponible, 0)
        self.assertTrue(JournalAudit.objects.filter(action="Lot bloqué", utilisateur=self.user).exists())
        self.client.post(reverse("stock:blocage", args=[lot.pk]))
        lot.refresh_from_db()
        self.assertFalse(lot.bloque)

    def test_blocage_exige_post(self):
        lot = self.lot(self.med())
        self.assertEqual(self.client.get(reverse("stock:blocage", args=[lot.pk])).status_code, 405)

    def test_caissier_consulte_sans_bloquer(self):
        lot = self.lot(self.med())
        self.client.force_login(creer_utilisateur("caisse", roles.CAISSIER))
        self.assertEqual(self.client.get(reverse("stock:lots")).status_code, 200)
        self.assertEqual(self.client.post(reverse("stock:blocage", args=[lot.pk])).status_code, 403)
        lot.refresh_from_db()
        self.assertFalse(lot.bloque)


class MouvementsTests(StockTestCase):
    def test_liste_et_filtre(self):
        lot = self.lot(self.med())
        MouvementStock.objects.create(lot=lot, type="entree", quantite=20, motif="Réception test", utilisateur=self.user)
        MouvementStock.objects.create(lot=lot, type="sortie", quantite=3, motif="Vente test")
        tous = self.client.get(reverse("stock:mouvements"))
        sorties = self.client.get(reverse("stock:mouvements"), {"type": "sortie"})
        recherche = self.client.get(reverse("stock:mouvements"), {"q": "Réception"})
        self.assertEqual(len(tous.context["page"]), 2)
        self.assertEqual([m.type for m in sorties.context["page"]], ["sortie"])
        self.assertEqual(len(recherche.context["page"]), 1)

    def test_acces_reserve(self):
        self.client.force_login(creer_utilisateur("caisse", roles.CAISSIER))
        self.assertEqual(self.client.get(reverse("stock:mouvements")).status_code, 403)


class InventaireTests(StockTestCase):
    def setUp(self):
        super().setUp()
        self.lot1 = self.lot(self.med("A"), "L1", quantite=20)
        self.lot2 = self.lot(self.med("B"), "L2", quantite=10)

    def poster(self, comptes, motif="Inventaire de test"):
        d = {"motif": motif}
        for lot, valeur in comptes.items():
            d[f"compte_{lot.pk}"] = valeur
        return self.client.post(reverse("stock:inventaire"), d, follow=True)

    def test_page_affichee(self):
        r = self.client.get(reverse("stock:inventaire"))
        self.assertContains(r, "L1")
        self.assertContains(r, "Quantité comptée")

    def test_correction_a_la_baisse_et_a_la_hausse(self):
        self.lot1.quantite_restante = 15
        self.lot1.save()
        self.poster({self.lot1: "18", self.lot2: "8"})
        self.lot1.refresh_from_db()
        self.lot2.refresh_from_db()
        self.assertEqual((self.lot1.quantite_restante, self.lot2.quantite_restante), (18, 8))
        corrections = MouvementStock.objects.filter(type=MouvementStock.Type.CORRECTION)
        self.assertEqual(corrections.count(), 2)
        m = corrections.get(lot=self.lot2)
        self.assertEqual((m.quantite, m.utilisateur), (2, self.user))
        self.assertIn("10 → 8", m.motif)
        self.assertIn("Inventaire de test", m.motif)

    def test_aucun_ecart_aucune_correction(self):
        r = self.poster({self.lot1: "20", self.lot2: "10"})
        self.assertContains(r, "aucun écart")
        self.assertEqual(MouvementStock.objects.count(), 0)

    def test_champ_vide_laisse_le_lot_inchange(self):
        self.poster({self.lot1: "", self.lot2: "5"})
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)

    def test_quantite_negative_refusee_et_rien_modifie(self):
        r = self.poster({self.lot1: "5", self.lot2: "-1"})
        self.assertContains(r, "négatif")
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)  # même la ligne valide n'est pas appliquée
        self.assertEqual(MouvementStock.objects.count(), 0)

    def test_quantite_superieure_a_la_quantite_recue_refusee(self):
        r = self.poster({self.lot1: "21"})
        self.assertContains(r, "quantité reçue")
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)

    def test_valeur_non_numerique_refusee(self):
        r = self.poster({self.lot1: "abc"})
        self.assertContains(r, "Nombre entier")

    def test_motif_obligatoire(self):
        r = self.poster({self.lot1: "5"}, motif="  ")
        self.assertContains(r, "motif")
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)

    def test_le_stock_ne_devient_jamais_negatif_au_niveau_service(self):
        with self.assertRaises(services.ErreurStock):
            services.corriger_inventaire(self.user, {self.lot1.pk: -3}, "test")
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)

    def test_service_atomique(self):
        with self.assertRaises(services.ErreurStock):
            services.corriger_inventaire(self.user, {self.lot1.pk: 5, self.lot2.pk: 999}, "test")
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)
        self.assertEqual(MouvementStock.objects.count(), 0)

    def test_inventaire_journalise(self):
        self.poster({self.lot1: "10"})
        self.assertTrue(JournalAudit.objects.filter(action="Inventaire enregistré").exists())

    def test_pharmacien_et_caissier_interdits(self):
        for role in (roles.PHARMACIEN, roles.CAISSIER, roles.RESPONSABLE_GESTION):
            self.client.force_login(creer_utilisateur(f"u_{role[:4]}", role))
            self.assertEqual(self.client.get(reverse("stock:inventaire")).status_code, 403, role)
            r = self.client.post(reverse("stock:inventaire"), {"motif": "x", f"compte_{self.lot1.pk}": "1"})
            self.assertEqual(r.status_code, 403)
        self.lot1.refresh_from_db()
        self.assertEqual(self.lot1.quantite_restante, 20)

    def test_visiteur_anonyme(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("stock:inventaire")).status_code, 302)
