from decimal import Decimal

from django.urls import reverse

from stock.models import LotStock, MouvementStock
from utilisateurs import roles
from utilisateurs.models import JournalAudit
from utilisateurs.outils_tests import creer_utilisateur
from ventes import services
from ventes.models import Paiement, RetourVente, Vente
from ventes.outils_tests import CaisseTestCase


class RetoursTestCase(CaisseTestCase):
    def setUp(self):
        super().setUp()
        self.pharmacien = creer_utilisateur("pharma", roles.PHARMACIEN)
        self.client.force_login(self.pharmacien)
        self.vente = self.vendre(5)               # 5 × 500 = 2500, pris dans le lot A
        self.ligne = self.vente.lignes.get()

    def retourner(self, quantite=2, remettre=False, motif="Produit non utilisé"):
        return services.retourner(
            self.pharmacien, self.vente.pk,
            [{"ligne_id": self.ligne.pk, "quantite": quantite, "remettre_en_stock": remettre}], motif)

    def restant_a(self):
        self.lot_a.refresh_from_db()
        return self.lot_a.quantite_restante


class RetourTests(RetoursTestCase):
    def test_retour_conserve_la_vente_et_calcule_le_remboursement(self):
        retour, = self.retourner(2)
        self.assertEqual(retour.montant_rembourse, Decimal("1000"))
        self.assertEqual((retour.enregistre_par, retour.motif), (self.pharmacien, "Produit non utilisé"))
        self.assertEqual(Vente.objects.count(), 1)
        self.assertEqual(self.vente.lignes.get().quantite, 5)  # vente d'origine intacte
        self.assertEqual(self.vente.total, Decimal("2500"))
        self.assertEqual(self.vente.total_rembourse, Decimal("1000"))

    def test_sans_remise_en_stock_le_stock_ne_change_pas(self):
        avant = self.restant_a()
        self.retourner(2, remettre=False)
        self.assertEqual(self.restant_a(), avant)
        self.assertFalse(MouvementStock.objects.filter(type="retour").exists())

    def test_remise_en_stock_d_un_produit_eligible(self):
        avant = self.restant_a()
        retour, = self.retourner(2, remettre=True)
        self.assertEqual(self.restant_a(), avant + 2)
        self.assertTrue(retour.remis_en_stock)
        m = MouvementStock.objects.get(type="retour")
        self.assertEqual((m.quantite, m.utilisateur), (2, self.pharmacien))

    def test_remise_en_stock_refusee_si_lot_perime_ou_bloque(self):
        self.lot_a.bloque = True
        self.lot_a.save()
        avant = self.restant_a()
        with self.assertRaises(services.ErreurVente):
            self.retourner(2, remettre=True)
        self.assertEqual(self.restant_a(), avant)
        self.assertEqual(RetourVente.objects.count(), 0)

    def test_remise_en_stock_refusee_si_depasse_la_quantite_recue(self):
        LotStock.objects.filter(pk=self.lot_a.pk).update(quantite_restante=10)  # lot « plein » (inventaire)
        with self.assertRaises(services.ErreurVente):
            self.retourner(1, remettre=True)
        self.assertEqual(RetourVente.objects.count(), 0)

    def test_quantite_superieure_a_la_quantite_vendue_refusee(self):
        with self.assertRaises(services.ErreurVente):
            self.retourner(6)

    def test_retours_cumules_limites_a_la_quantite_vendue(self):
        self.retourner(3)
        self.retourner(2)
        with self.assertRaises(services.ErreurVente):
            self.retourner(1)
        self.assertEqual(self.ligne.quantite_retournable, 0)
        self.assertTrue(self.vente.est_entierement_retournee)

    def test_motif_obligatoire(self):
        with self.assertRaises(services.ErreurVente):
            self.retourner(1, motif="  ")

    def test_quantite_nulle_refusee(self):
        with self.assertRaises(services.ErreurVente):
            self.retourner(0)

    def test_aucune_ligne_refusee(self):
        with self.assertRaises(services.ErreurVente):
            services.retourner(self.pharmacien, self.vente.pk, [], "motif")

    def test_ligne_d_une_autre_vente_refusee(self):
        autre = self.vendre(1).lignes.get()
        with self.assertRaises(services.ErreurVente):
            services.retourner(self.pharmacien, self.vente.pk,
                               [{"ligne_id": autre.pk, "quantite": 1}], "motif")

    def test_atomicite_une_erreur_annule_tout(self):
        autre = self.autre_medicament()
        self.creer_lot(autre, "X", quantite=5)
        vente = self.vendre(2, medicament=autre)
        ligne2 = vente.lignes.get()
        with self.assertRaises(services.ErreurVente):
            services.retourner(self.pharmacien, self.vente.pk, [
                {"ligne_id": self.ligne.pk, "quantite": 1, "remettre_en_stock": True},
                {"ligne_id": self.ligne.pk, "quantite": 99},
            ], "motif")
        self.assertEqual((RetourVente.objects.count(), self.restant_a()), (0, 5))

    def test_retour_journalise(self):
        self.retourner(1)
        self.assertTrue(JournalAudit.objects.filter(action="Retour enregistré", utilisateur=self.pharmacien).exists())

    def test_retour_via_la_page(self):
        r = self.client.post(reverse("ventes:retour", args=[self.vente.pk]), {
            f"quantite_{self.ligne.pk}": "2", f"remettre_{self.ligne.pk}": "on", "motif": "Erreur de délivrance"},
            follow=True)
        self.assertRedirects(r, reverse("ventes:detail", args=[self.vente.pk]))
        self.assertContains(r, "Erreur de délivrance")
        self.assertEqual(self.restant_a(), 7)

    def test_page_retour_erreurs_de_saisie(self):
        r = self.client.post(reverse("ventes:retour", args=[self.vente.pk]), {
            f"quantite_{self.ligne.pk}": "abc", "motif": "x"})
        self.assertContains(r, "quantité invalide")
        r = self.client.post(reverse("ventes:retour", args=[self.vente.pk]), {
            f"quantite_{self.ligne.pk}": "9", "motif": "x"})
        self.assertContains(r, "peuvent encore l")
        self.assertEqual(RetourVente.objects.count(), 0)

    def test_caissier_ne_peut_pas_enregistrer_un_retour(self):
        self.client.force_login(self.caissier)
        self.assertEqual(self.client.get(reverse("ventes:retour", args=[self.vente.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("ventes:annuler", args=[self.vente.pk]), {"motif": "x"}).status_code, 403)
        self.assertEqual(RetourVente.objects.count(), 0)


class AnnulationTests(RetoursTestCase):
    def test_annulation_par_operation_compensatoire(self):
        avant = self.restant_a()
        vente, non_remises = services.annuler_vente(self.pharmacien, self.vente.pk, "Erreur de caisse")
        self.assertEqual((vente.statut, non_remises), (Vente.Statut.ANNULEE, 0))
        self.assertEqual(self.restant_a(), avant + 5)
        self.assertEqual(Vente.objects.count(), 1)             # la vente n'est pas supprimée
        retour = RetourVente.objects.get()
        self.assertEqual((retour.quantite, retour.montant_rembourse, retour.remis_en_stock), (5, Decimal("2500"), True))
        self.assertIn("Erreur de caisse", retour.motif)
        self.assertEqual(vente.total_rembourse, Decimal("2500"))
        self.assertTrue(JournalAudit.objects.filter(action="Vente annulée", utilisateur=self.pharmacien).exists())

    def test_annulation_apres_un_retour_partiel(self):
        self.retourner(2)
        services.annuler_vente(self.pharmacien, self.vente.pk, "Reste")
        self.assertEqual(sum(r.quantite for r in RetourVente.objects.all()), 5)
        self.assertEqual(self.vente.total_rembourse, Decimal("2500"))

    def test_annulation_sans_remise_en_stock(self):
        avant = self.restant_a()
        services.annuler_vente(self.pharmacien, self.vente.pk, "x", remettre_en_stock=False)
        self.assertEqual(self.restant_a(), avant)

    def test_lot_non_eligible_pas_remis_en_stock(self):
        self.lot_a.bloque = True
        self.lot_a.save()
        avant = self.restant_a()
        vente, non_remises = services.annuler_vente(self.pharmacien, self.vente.pk, "x")
        self.assertEqual(non_remises, 1)
        self.assertEqual(self.restant_a(), avant)
        self.assertEqual(vente.statut, Vente.Statut.ANNULEE)

    def test_double_annulation_refusee(self):
        services.annuler_vente(self.pharmacien, self.vente.pk, "x")
        with self.assertRaises(services.ErreurVente):
            services.annuler_vente(self.pharmacien, self.vente.pk, "x")
        self.assertEqual(self.restant_a(), 10)  # remis une seule fois

    def test_motif_obligatoire(self):
        with self.assertRaises(services.ErreurVente):
            services.annuler_vente(self.pharmacien, self.vente.pk, "")
        self.vente.refresh_from_db()
        self.assertEqual(self.vente.statut, Vente.Statut.VALIDEE)

    def test_paiements_en_attente_deviennent_echoues(self):
        vente = self.vendre(1, mode="mobile_money")
        services.annuler_vente(self.pharmacien, vente.pk, "x")
        self.assertEqual(vente.paiements.get().statut, Paiement.Statut.ECHOUE)

    def test_vente_annulee_plus_de_retour_ni_de_paiement(self):
        services.annuler_vente(self.pharmacien, self.vente.pk, "x")
        with self.assertRaises(services.ErreurVente):
            self.retourner(1)
        with self.assertRaises(services.ErreurVente):
            services.ajouter_paiement(self.pharmacien, self.vente.pk, "especes", Decimal("1"))

    def test_annulation_via_la_page(self):
        page = self.client.get(reverse("ventes:annuler", args=[self.vente.pk]))
        self.assertContains(page, "opération compensatoire")
        self.vente.refresh_from_db()
        self.assertEqual(self.vente.statut, Vente.Statut.VALIDEE)  # GET = confirmation seulement
        r = self.client.post(reverse("ventes:annuler", args=[self.vente.pk]),
                             {"motif": "Client parti", "remettre": "on"}, follow=True)
        self.assertContains(r, "est annulée")
        self.vente.refresh_from_db()
        self.assertEqual(self.vente.statut, Vente.Statut.ANNULEE)

    def test_annulation_via_la_page_sans_motif(self):
        r = self.client.post(reverse("ventes:annuler", args=[self.vente.pk]), {"motif": ""})
        self.assertContains(r, "motif")
        self.vente.refresh_from_db()
        self.assertEqual(self.vente.statut, Vente.Statut.VALIDEE)

    def test_la_vente_reste_consultable_apres_annulation(self):
        services.annuler_vente(self.pharmacien, self.vente.pk, "x")
        r = self.client.get(reverse("ventes:detail", args=[self.vente.pk]))
        self.assertContains(r, "Annulée")
        self.assertContains(r, "Retours et remboursements")
