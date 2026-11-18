from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from achats.models import CommandeAchat
from medicaments.models import Medicament
from rapports import statistiques
from rapports.outils_tests import RapportsTestCase
from stock.models import LotStock
from utilisateurs import roles
from utilisateurs.outils_tests import creer_utilisateur
from ventes import services
from ventes.models import Paiement


class ChiffreAffairesTests(RapportsTestCase):
    def stats(self, financieres=True):
        return statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui, financieres)

    def test_chiffre_d_affaires_somme_des_ventes_validees(self):
        self.vendre(3)   # 1500
        self.vendre(2)   # 1000
        s = self.stats()
        self.assertEqual((s["nombre_ventes"], s["ca"]), (2, Decimal("2500")))

    def test_ventes_annulees_exclues(self):
        v = self.vendre(3)
        self.vendre(2)
        services.annuler_vente(self.caissier, v.pk, "erreur")
        s = self.stats()
        self.assertEqual((s["nombre_ventes"], s["ca"]), (1, Decimal("1000")))

    def test_retours_deduits_du_chiffre_d_affaires(self):
        vente = self.vendre(5)  # 2500
        ligne = vente.lignes.get()
        services.retourner(self.caissier, vente.pk, [{"ligne_id": ligne.pk, "quantite": 2}], "retour")
        self.assertEqual(self.stats()["ca"], Decimal("1500"))

    def test_prix_fige_utilise_meme_si_le_prix_change(self):
        self.vendre(2)
        self.med.prix_vente = Decimal("9999")
        self.med.save()
        self.assertEqual(self.stats()["ca"], Decimal("1000"))

    def test_periode_respectee(self):
        self.vendre(2)
        demain = self.aujourdhui + timedelta(days=1)
        hier = self.aujourdhui - timedelta(days=1)
        self.assertEqual(statistiques.statistiques_ventes(demain, demain)["ca"], Decimal("0"))
        self.assertEqual(statistiques.statistiques_ventes(hier, hier)["ca"], Decimal("0"))
        self.assertEqual(statistiques.statistiques_ventes(hier, demain)["ca"], Decimal("1000"))

    def test_ventes_du_jour(self):
        self.vendre(2)
        self.vendre(1)
        jour = statistiques.ventes_du_jour()
        self.assertEqual((jour["nombre"], jour["ca"]), (2, Decimal("1500")))

    def test_aucune_vente(self):
        s = self.stats()
        self.assertEqual((s["nombre_ventes"], s["ca"], s["encaissements"], s["marge_brute"]),
                         (0, Decimal("0"), Decimal("0"), Decimal("0")))
        self.assertEqual((s["par_jour"], s["produits_les_plus_vendus"]), ([], []))


class EncaissementsEtMargeTests(RapportsTestCase):
    def stats(self):
        return statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui, financieres=True)

    def test_le_chiffre_d_affaires_n_est_pas_les_encaissements(self):
        self.vendre(2, mode="especes")         # 1000 encaissé
        self.vendre(4, mode="mobile_money")    # 2000 vendu mais en attente
        s = self.stats()
        self.assertEqual(s["ca"], Decimal("3000"))
        self.assertEqual(s["encaissements"], Decimal("1000"))
        self.assertEqual(s["en_attente"], Decimal("2000"))

    def test_encaissement_apres_confirmation_du_paiement(self):
        vente = self.vendre(4, mode="mobile_money")
        services.confirmer_paiement(self.caissier, vente.paiements.get().pk, "TX-1")
        self.assertEqual(self.stats()["encaissements"], Decimal("2000"))
        self.assertEqual(self.stats()["en_attente"], Decimal("0"))

    def test_paiement_echoue_jamais_encaisse(self):
        vente = self.vendre(4, mode="mobile_money")
        services.declarer_paiement_echoue(self.caissier, vente.paiements.get().pk)
        self.assertEqual(self.stats()["encaissements"], Decimal("0"))

    def test_remboursements_distincts(self):
        vente = self.vendre(5)
        services.retourner(self.caissier, vente.pk, [{"ligne_id": vente.lignes.get().pk, "quantite": 2}], "r")
        s = self.stats()
        self.assertEqual((s["encaissements"], s["remboursements"]), (Decimal("2500"), Decimal("1000")))

    def test_marge_brute_avec_cout_de_repli_du_medicament(self):
        self.vendre(4)  # CA 2000, coût 4 × 300 (prix d'achat du médicament, lot sans réception)
        s = self.stats()
        self.assertEqual((s["cout_achat"], s["marge_brute"]), (Decimal("1200"), Decimal("800")))

    def test_marge_brute_avec_cout_reel_du_lot(self):
        autre = self.autre_medicament("Ibuprofène", prix="1000")
        autre.prix_achat = Decimal("900")   # prix d'achat « courant » différent du coût réel du lot
        autre.save()
        self.receptionner(autre, 10, "400", numero_lot="IBU-1")   # coût réel : 400
        self.vendre(5, medicament=autre)                          # CA 5000
        s = self.stats()
        self.assertEqual((s["ca"], s["cout_achat"], s["marge_brute"]),
                         (Decimal("5000"), Decimal("2000"), Decimal("3000")))

    def test_cout_pondere_sur_plusieurs_receptions_du_meme_lot(self):
        autre = self.autre_medicament("Vitamine", prix="1000")
        self.receptionner(autre, 10, "400", numero_lot="V-1")
        self.receptionner(autre, 10, "600", numero_lot="V-1")   # même lot : coût moyen 500
        self.vendre(2, medicament=autre)
        self.assertEqual(self.stats()["cout_achat"], Decimal("1000"))

    def test_marge_diminuee_par_les_retours(self):
        vente = self.vendre(5)  # CA 2500, coût 1500
        services.retourner(self.caissier, vente.pk, [{"ligne_id": vente.lignes.get().pk, "quantite": 5}], "tout")
        s = self.stats()
        self.assertEqual((s["ca"], s["cout_achat"], s["marge_brute"]), (Decimal("0"),) * 3)

    def test_sans_droit_financier_aucun_chiffre_sensible(self):
        self.vendre(2)
        s = statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui, financieres=False)
        for cle in ("encaissements", "cout_achat", "marge_brute", "remboursements"):
            self.assertNotIn(cle, s)


class ProduitsEtJoursTests(RapportsTestCase):
    def test_produits_les_plus_vendus_dans_l_ordre(self):
        autre = self.autre_medicament("Ibuprofène")
        self.creer_lot(autre, "I1", quantite=50)
        self.vendre(2)
        self.vendre(7, medicament=autre)
        self.vendre(3)
        top = statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui)["produits_les_plus_vendus"]
        self.assertEqual([(t["medicament"].nom_commercial, t["quantite"]) for t in top],
                         [("Ibuprofène", 7), ("Paracétamol", 5)])

    def test_produit_entierement_retourne_absent_du_classement(self):
        vente = self.vendre(2)
        services.retourner(self.caissier, vente.pk, [{"ligne_id": vente.lignes.get().pk, "quantite": 2}], "r")
        top = statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui)["produits_les_plus_vendus"]
        self.assertEqual(top, [])

    def test_classement_limite_a_cinq(self):
        for i in range(7):
            m = self.autre_medicament(f"Med{i}")
            self.creer_lot(m, f"L{i}", quantite=10)
            self.vendre(1, medicament=m)
        top = statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui)["produits_les_plus_vendus"]
        self.assertEqual(len(top), 5)

    def test_ventes_par_jour(self):
        self.vendre(2)
        self.vendre(1)
        jours = statistiques.statistiques_ventes(self.aujourdhui, self.aujourdhui)["par_jour"]
        self.assertEqual(len(jours), 1)
        self.assertEqual((jours[0]["jour"], jours[0]["nombre"], jours[0]["ca"]),
                         (self.aujourdhui, 2, Decimal("1500")))


class StatistiquesStockTests(RapportsTestCase):
    def test_compteurs(self):
        LotStock.objects.all().delete()
        vide = self.autre_medicament("Vide")                          # rupture
        bas = self.autre_medicament("Bas", seuil_alerte=10)           # faible (5 < 10)
        egal = self.autre_medicament("Egal", seuil_alerte=10)         # 10 : pas faible
        self.creer_lot(bas, "B", quantite=5)
        self.creer_lot(egal, "E", quantite=10)
        self.creer_lot(egal, "P", jours=10, quantite=1)               # lot proche (et vendable)
        perime = self.autre_medicament("Perime")
        self.creer_lot(perime, "PER", jours=-3, quantite=4)           # périmé encore en stock
        Medicament.objects.filter(pk=self.med.pk).update(statut=Medicament.Statut.ARCHIVE)
        s = statistiques.statistiques_stock()
        self.assertEqual(s["medicaments_actifs"], 4)                  # Vide, Bas, Egal, Perime
        self.assertEqual(s["ruptures"], 2)                            # Vide + Perime (seul lot périmé)
        self.assertEqual(s["stocks_faibles"], 1)
        self.assertEqual(s["lots_proches"], 1)
        self.assertEqual(s["lots_perimes"], 1)

    def test_lot_vide_ou_peremption_lointaine_non_signales(self):
        LotStock.objects.all().delete()
        self.creer_lot(self.med, "LOIN", jours=500, quantite=5)
        s = statistiques.statistiques_stock()
        self.assertEqual((s["lots_proches"], s["lots_perimes"]), (0, 0))

    def test_seuil_de_proximite_configurable(self):
        with self.settings(JOURS_ALERTE_PEREMPTION=60):
            self.assertEqual(statistiques.statistiques_stock()["lots_proches"], 1)    # lot A à 30 j
        with self.settings(JOURS_ALERTE_PEREMPTION=10):
            self.assertEqual(statistiques.statistiques_stock()["lots_proches"], 0)


class StatistiquesAchatsTests(RapportsTestCase):
    def test_achats_de_la_periode(self):
        _, reception = self.receptionner(self.med, 10, "300")           # commande 3000, réceptionnée
        brouillon = CommandeAchat.objects.create(
            fournisseur=reception.commande.fournisseur, cree_par=self.caissier)  # brouillon : ignoré
        annulee = CommandeAchat.objects.create(
            fournisseur=reception.commande.fournisseur, cree_par=self.caissier,
            statut=CommandeAchat.Statut.ANNULEE)
        s = statistiques.statistiques_achats(self.aujourdhui, self.aujourdhui)
        self.assertEqual((s["nombre_commandes"], s["montant_commande"], s["montant_receptionne"]),
                         (1, Decimal("3000"), Decimal("3000")))

    def test_periode_sans_achat(self):
        demain = self.aujourdhui + timedelta(days=1)
        s = statistiques.statistiques_achats(demain, demain)
        self.assertEqual((s["nombre_commandes"], s["montant_commande"]), (0, Decimal("0")))


class TableauDeBordTests(RapportsTestCase):
    def accueil(self, utilisateur=None, **params):
        if utilisateur:
            self.client.force_login(utilisateur)
        return self.client.get(reverse("accueil"), params)

    def test_anonyme_renvoye_vers_la_connexion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 302)

    def test_responsable_de_gestion_voit_tout(self):
        self.vendre(2, mode="mobile_money")
        r = self.accueil(creer_utilisateur("gestion", roles.RESPONSABLE_GESTION))
        self.assertContains(r, "Médicaments actifs")
        self.assertContains(r, "Chiffre d'affaires")
        self.assertContains(r, "Encaissements")
        self.assertContains(r, "Marge commerciale brute")
        self.assertContains(r, "pas un bénéfice net")
        self.assertContains(r, "Produits les plus vendus")
        self.assertEqual(r.context["ventes"]["ca"], Decimal("1000"))
        self.assertEqual(r.context["ventes"]["encaissements"], Decimal("0"))

    def test_caissier_voit_stock_et_ventes_du_jour_sans_chiffres_financiers(self):
        self.vendre(2)
        r = self.accueil(self.caissier)
        self.assertContains(r, "Ventes du jour")
        self.assertContains(r, "Stocks faibles")
        self.assertNotContains(r, "Marge commerciale")
        self.assertNotContains(r, "Encaissements")
        self.assertNotContains(r, "Chiffres de la période")
        self.assertNotIn("achats", r.context)

    def test_gestionnaire_de_stock_voit_le_stock_mais_pas_les_ventes(self):
        r = self.accueil(creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK))
        self.assertContains(r, "Médicaments actifs")
        self.assertNotContains(r, "Ventes du jour")
        self.assertNotContains(r, "Marge commerciale")

    def test_utilisateur_sans_role_voit_l_accueil_simple(self):
        r = self.accueil(creer_utilisateur("sans_role"))
        self.assertContains(r, "Bienvenue sur PharmaGest")
        self.assertNotContains(r, "Médicaments actifs")

    def test_valeurs_calculees_a_partir_des_donnees(self):
        self.vendre(3)
        r = self.accueil(creer_utilisateur("gestion", roles.RESPONSABLE_GESTION))
        self.assertEqual(r.context["ventes_du_jour"]["nombre"], 1)
        self.assertEqual(r.context["stock"]["medicaments_actifs"], 1)
        self.assertEqual(r.context["ventes"]["ca"], Decimal("1500"))

    def test_periode_choisie_et_periode_invalide(self):
        self.vendre(1)
        gestion = creer_utilisateur("gestion", roles.RESPONSABLE_GESTION)
        hier = (self.aujourdhui - timedelta(days=2)).isoformat()
        avant = (self.aujourdhui - timedelta(days=1)).isoformat()
        r = self.accueil(gestion, du=hier, au=avant)
        self.assertEqual(r.context["ventes"]["ca"], Decimal("0"))
        r = self.accueil(gestion, du="n'importe quoi", au="")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["ventes"]["ca"], Decimal("500"))
        # dates inversées : remises dans l'ordre
        r = self.accueil(gestion, du=self.aujourdhui.isoformat(), au=hier)
        self.assertEqual(r.context["du"], self.aujourdhui - timedelta(days=2))

    def test_alertes_affichees(self):
        LotStock.objects.create(medicament=self.med, numero_lot="PER", quantite_recue=3, quantite_restante=3,
                                date_peremption=self.aujourdhui - timedelta(days=2))
        r = self.accueil(creer_utilisateur("pharma", roles.PHARMACIEN))
        self.assertContains(r, "Périmé")
        self.assertContains(r, "PER")
