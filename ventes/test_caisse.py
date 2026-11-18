import uuid
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from clients.models import Client
from medicaments.models import Medicament
from stock.models import LotStock, MouvementStock
from utilisateurs import roles
from utilisateurs.models import JournalAudit
from utilisateurs.outils_tests import creer_utilisateur
from ventes import services
from ventes.models import LigneVente, Paiement, Vente
from ventes.outils_tests import CaisseTestCase
from ventes.panier import CLE


class PanierTests(CaisseTestCase):
    def ajouter(self, quantite=1, lot="", medicament=None):
        return self.client.post(reverse("ventes:panier_ajouter"), {
            "medicament": (medicament or self.med).pk, "quantite": quantite, "lot": lot}, follow=True)

    def lignes(self):
        return self.client.session.get(CLE, {}).get("lignes", [])

    def test_ajout_au_panier(self):
        self.ajouter(2)
        self.assertEqual(self.lignes(), [{"medicament_id": self.med.pk, "quantite": 2, "lot_id": None}])

    def test_ajouts_successifs_cumules(self):
        self.ajouter(2)
        self.ajouter(3)
        self.assertEqual(self.lignes()[0]["quantite"], 5)

    def test_code_barres_exact_ajoute_une_unite(self):
        r = self.client.post(reverse("ventes:rechercher"), {"q": "123456"}, follow=True)
        self.assertEqual(self.lignes()[0]["quantite"], 1)
        self.assertContains(r, "ajouté(s) au panier")

    def test_recherche_par_nom_affiche_les_resultats(self):
        r = self.client.post(reverse("ventes:rechercher"), {"q": "parac"}, follow=True)
        self.assertContains(r, "Paracétamol")
        self.assertEqual(self.lignes(), [])

    def test_quantite_nulle_ou_negative_refusee(self):
        for q in ("0", "-2", "abc", ""):
            r = self.ajouter(q)
            self.assertContains(r, "au moins 1")
        self.assertEqual(self.lignes(), [])

    def test_quantite_superieure_au_stock_refusee(self):
        r = self.ajouter(21)
        self.assertContains(r, "Stock insuffisant")
        self.assertEqual(self.lignes(), [])

    def test_stock_cumule_dans_le_panier_verifie(self):
        self.ajouter(15)
        r = self.ajouter(6)
        self.assertContains(r, "Stock insuffisant")
        self.assertEqual(self.lignes()[0]["quantite"], 15)

    def test_lot_perime_ou_bloque_non_vendable(self):
        perime = self.creer_lot(self.med, "PER", jours=-1)
        bloque = self.creer_lot(self.med, "BLO", bloque=True)
        for lot in (perime, bloque):
            r = self.ajouter(1, lot=lot.pk)
            self.assertContains(r, "pas vendable")
        self.assertEqual(self.lignes(), [])

    def test_medicament_archive_refuse(self):
        self.med.statut = Medicament.Statut.ARCHIVE
        self.med.save()
        r = self.ajouter(1)
        self.assertContains(r, "archivé")

    def test_modifier_retirer_vider(self):
        self.ajouter(2)
        self.client.post(reverse("ventes:panier_modifier", args=[0]), {"quantite": "5"})
        self.assertEqual(self.lignes()[0]["quantite"], 5)
        r = self.client.post(reverse("ventes:panier_modifier", args=[0]), {"quantite": "99"}, follow=True)
        self.assertContains(r, "Stock insuffisant")
        self.assertEqual(self.lignes()[0]["quantite"], 5)
        self.client.post(reverse("ventes:panier_retirer", args=[0]))
        self.assertEqual(self.lignes(), [])
        self.ajouter(1)
        self.client.post(reverse("ventes:panier_vider"))
        self.assertEqual(self.lignes(), [])

    def test_affichage_du_panier_avec_total_et_lots(self):
        self.ajouter(12)
        r = self.client.get(reverse("ventes:caisse"))
        self.assertEqual(r.context["total"], Decimal("6000"))
        self.assertContains(r, "10 × lot A")
        self.assertContains(r, "2 × lot B")
        self.assertTrue(r.context["valide"])

    def test_aucune_vente_tant_que_non_validee(self):
        self.ajouter(3)
        self.assertEqual(Vente.objects.count(), 0)
        self.assertEqual(self.stock(), 20)


class ValidationDeVenteTests(CaisseTestCase):
    def valider_via_caisse(self, quantite=3, mode="especes", client_id=""):
        self.client.post(reverse("ventes:panier_ajouter"), {
            "medicament": self.med.pk, "quantite": quantite, "lot": ""})
        jeton = self.client.session[CLE]["jeton"]
        return self.client.post(reverse("ventes:valider"), {
            "jeton": jeton, "mode": mode, "client": client_id}, follow=True)

    def test_vendre_3_unites_diminue_le_stock_de_3_une_seule_fois(self):  # RG06
        avant = self.stock()
        r = self.valider_via_caisse(3)
        vente = Vente.objects.get()
        self.assertRedirects(r, reverse("ventes:detail", args=[vente.pk]))
        self.assertEqual(self.stock(), avant - 3)
        self.assertEqual(MouvementStock.objects.filter(type="sortie").count(), 1)

    def test_vente_enregistre_auteur_prix_et_lot(self):
        self.valider_via_caisse(3)
        vente = Vente.objects.get()
        ligne = vente.lignes.get()
        self.assertEqual(vente.vendeur, self.caissier)
        self.assertEqual((ligne.lot, ligne.quantite, ligne.prix_applique), (self.lot_a, 3, Decimal("500")))
        mouvement = MouvementStock.objects.get(type="sortie")
        self.assertEqual((mouvement.utilisateur, mouvement.quantite), (self.caissier, 3))
        self.assertTrue(JournalAudit.objects.filter(action="Vente enregistrée", utilisateur=self.caissier).exists())

    def test_panier_vide_apres_la_vente(self):
        self.valider_via_caisse(3)
        self.assertEqual(self.client.session[CLE]["lignes"], [])

    def test_double_envoi_du_meme_formulaire(self):  # pas de double sortie
        self.client.post(reverse("ventes:panier_ajouter"), {"medicament": self.med.pk, "quantite": 3, "lot": ""})
        jeton = self.client.session[CLE]["jeton"]
        donnees = {"jeton": jeton, "mode": "especes", "client": ""}
        self.client.post(reverse("ventes:valider"), donnees)
        r = self.client.post(reverse("ventes:valider"), donnees, follow=True)
        self.assertContains(r, "déjà été validée")
        self.assertEqual(Vente.objects.count(), 1)
        self.assertEqual(self.stock(), 17)

    def test_jeton_inconnu_refuse(self):
        self.client.post(reverse("ventes:panier_ajouter"), {"medicament": self.med.pk, "quantite": 3, "lot": ""})
        r = self.client.post(reverse("ventes:valider"), {"jeton": str(uuid.uuid4()), "mode": "especes"}, follow=True)
        self.assertContains(r, "panier a changé")
        self.assertEqual(Vente.objects.count(), 0)
        self.assertEqual(self.stock(), 20)

    def test_rejeu_du_jeton_au_niveau_service(self):
        jeton = uuid.uuid4()
        v1 = self.vendre(3, jeton=jeton)
        v2, creee = services.valider_vente(
            self.caissier, [{"medicament_id": self.med.pk, "quantite": 3, "lot_id": None}],
            "especes", jeton)
        self.assertEqual((v1.pk, creee), (v2.pk, False))
        self.assertEqual(self.stock(), 17)

    def test_vendre_plus_que_le_stock_est_refuse(self):
        with self.assertRaises(services.ErreurVente):
            self.vendre(21)
        self.assertEqual((Vente.objects.count(), self.stock(), MouvementStock.objects.count()), (0, 20, 0))

    def test_deux_ventes_ne_rendent_jamais_le_stock_negatif(self):
        self.vendre(15)
        with self.assertRaises(services.ErreurVente):
            self.vendre(6)
        self.assertEqual(self.stock(), 5)
        self.assertGreaterEqual(min(LotStock.objects.values_list("quantite_restante", flat=True)), 0)

    def test_stock_perime_non_vendu_meme_en_automatique(self):
        LotStock.objects.all().delete()
        self.creer_lot(self.med, "PER", jours=-1, quantite=50)
        with self.assertRaises(services.ErreurVente):
            self.vendre(1)

    def test_lot_perime_ou_bloque_refuse_au_niveau_service(self):  # RG08
        perime = self.creer_lot(self.med, "PER", jours=-1)
        bloque = self.creer_lot(self.med, "BLO", bloque=True)
        for lot in (perime, bloque):
            with self.assertRaises(services.ErreurVente):
                self.vendre(1, lot_id=lot.pk)
        self.assertEqual(Vente.objects.count(), 0)

    def test_methode_fefo_sur_plusieurs_lots(self):
        vente = self.vendre(12)
        lignes = {l.lot.numero_lot: l.quantite for l in vente.lignes.all()}
        self.assertEqual(lignes, {"A": 10, "B": 2})
        self.lot_a.refresh_from_db()
        self.lot_b.refresh_from_db()
        self.assertEqual((self.lot_a.quantite_restante, self.lot_b.quantite_restante), (0, 8))

    def test_fefo_ignore_les_lots_inutilisables(self):
        LotStock.objects.all().delete()
        self.creer_lot(self.med, "PERIME", jours=-1)
        self.creer_lot(self.med, "BLOQUE", jours=5, bloque=True)
        bon = self.creer_lot(self.med, "BON", jours=200)
        vente = self.vendre(2)
        self.assertEqual(vente.lignes.get().lot, bon)

    def test_lot_choisi_manuellement(self):
        vente = self.vendre(4, lot_id=self.lot_b.pk)
        self.assertEqual(vente.lignes.get().lot, self.lot_b)
        self.lot_a.refresh_from_db()
        self.assertEqual(self.lot_a.quantite_restante, 10)

    def test_lot_choisi_insuffisant_refuse(self):
        with self.assertRaises(services.ErreurVente):
            self.vendre(11, lot_id=self.lot_a.pk)

    def test_prix_fige_apres_changement_du_prix(self):  # RG12
        vente = self.vendre(2)
        self.med.prix_vente = Decimal("999")
        self.med.save()
        self.assertEqual(vente.lignes.get().prix_applique, Decimal("500"))
        self.assertEqual(vente.total, Decimal("1000"))

    def test_atomicite_une_ligne_en_erreur_annule_toute_la_vente(self):
        autre = self.autre_medicament()
        self.creer_lot(autre, "X", quantite=2)
        with self.assertRaises(services.ErreurVente):
            services.valider_vente(self.caissier, [
                {"medicament_id": self.med.pk, "quantite": 5, "lot_id": None},
                {"medicament_id": autre.pk, "quantite": 50, "lot_id": None},
            ], "especes", uuid.uuid4())
        self.assertEqual((Vente.objects.count(), LigneVente.objects.count(), MouvementStock.objects.count()), (0, 0, 0))
        self.assertEqual(self.stock(), 20)

    def test_sortie_conditionnelle_refuse_un_stock_devenu_insuffisant(self):
        # Simule une seconde validation qui a lu un stock devenu obsolète
        obsolete = LotStock.objects.get(pk=self.lot_a.pk)
        LotStock.objects.filter(pk=self.lot_a.pk).update(quantite_restante=2)
        self.assertEqual(obsolete.quantite_restante, 10)
        with self.assertRaises(services.ErreurVente):
            services._sortir(self.lot_a.pk, 5)
        self.lot_a.refresh_from_db()
        self.assertEqual(self.lot_a.quantite_restante, 2)

    def test_validation_simultanee_perdante_recoit_un_message_clair(self):
        # Sur SQLite, la transaction perdante échoue avec « base verrouillée » : pas de page d'erreur
        from unittest import mock
        from django.db import OperationalError
        with mock.patch.object(services, "_valider_vente", side_effect=OperationalError("database is locked")):
            with self.assertRaises(services.ErreurVente) as ctx:
                self.vendre(1)
        self.assertIn("réessayez", str(ctx.exception))

    def test_panier_vide_refuse(self):
        with self.assertRaises(services.ErreurVente):
            services.valider_vente(self.caissier, [], "especes", uuid.uuid4())

    def test_mode_de_paiement_invalide_refuse(self):
        with self.assertRaises(services.ErreurVente):
            self.vendre(1, mode="troc")
        self.assertEqual(self.stock(), 20)

    def test_medicament_archive_entre_temps_refuse(self):
        self.client.post(reverse("ventes:panier_ajouter"), {"medicament": self.med.pk, "quantite": 1, "lot": ""})
        self.med.statut = Medicament.Statut.ARCHIVE
        self.med.save()
        jeton = self.client.session[CLE]["jeton"]
        r = self.client.post(reverse("ventes:valider"), {"jeton": jeton, "mode": "especes"}, follow=True)
        self.assertContains(r, "archivé")
        self.assertEqual(Vente.objects.count(), 0)

    def test_vente_avec_client_et_vente_comptoir(self):
        client = Client.objects.create(nom="Client Test")
        v1 = self.vendre(1, client=client)
        v2 = self.vendre(1)
        self.assertEqual((v1.client, v2.client), (client, None))

    def test_client_inactif_refuse(self):
        inactif = Client.objects.create(nom="Inactif", actif=False)
        with self.assertRaises(services.ErreurVente):
            self.vendre(1, client=inactif)

    def test_vente_validee_jamais_supprimee(self):  # RG10
        vente = self.vendre(1)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            vente.delete()


class PaiementsTests(CaisseTestCase):
    def test_especes_confirme_immediatement(self):
        vente = self.vendre(2, mode="especes")
        p = vente.paiements.get()
        self.assertEqual((p.statut, p.montant), (Paiement.Statut.CONFIRME, Decimal("1000")))
        self.assertEqual(vente.libelle_paiement, "Payée")

    def test_mobile_money_en_attente_jusqu_a_verification(self):
        vente = self.vendre(2, mode="mobile_money")
        p = vente.paiements.get()
        self.assertEqual(p.statut, Paiement.Statut.EN_ATTENTE)
        self.assertEqual((vente.total_paye, vente.libelle_paiement), (Decimal("0"), "Paiement en attente"))

    def test_confirmation_exige_une_reference(self):
        p = self.vendre(2, mode="mobile_money").paiements.get()
        with self.assertRaises(services.ErreurVente):
            services.confirmer_paiement(self.caissier, p.pk, "")
        services.confirmer_paiement(self.caissier, p.pk, "TX-123")
        p.refresh_from_db()
        self.assertEqual((p.statut, p.reference_transaction), (Paiement.Statut.CONFIRME, "TX-123"))

    def test_confirmation_via_la_page(self):
        vente = self.vendre(2, mode="mobile_money")
        p = vente.paiements.get()
        self.client.post(reverse("ventes:paiement_confirmer", args=[p.pk]), {"reference": "TX-9"})
        p.refresh_from_db()
        self.assertEqual(p.statut, Paiement.Statut.CONFIRME)
        self.assertTrue(JournalAudit.objects.filter(action="Paiement confirmé").exists())

    def test_paiement_confirme_ne_se_reconfirme_pas(self):
        p = self.vendre(1).paiements.get()
        with self.assertRaises(services.ErreurVente):
            services.confirmer_paiement(self.caissier, p.pk, "X")

    def test_paiement_declare_echoue(self):
        p = self.vendre(2, mode="mobile_money").paiements.get()
        services.declarer_paiement_echoue(self.caissier, p.pk)
        p.refresh_from_db()
        self.assertEqual(p.statut, Paiement.Statut.ECHOUE)
        self.assertEqual(p.vente.total_paye, Decimal("0"))

    def test_paiement_partiel_puis_solde(self):
        vente = self.vendre(2, mode="mobile_money")  # 1000 en attente
        p = vente.paiements.get()
        services.declarer_paiement_echoue(self.caissier, p.pk)
        services.ajouter_paiement(self.caissier, vente.pk, "especes", Decimal("400"))
        self.assertEqual((vente.total_paye, vente.reste_a_payer, vente.libelle_paiement),
                         (Decimal("400"), Decimal("600"), "Partiellement payée"))
        services.ajouter_paiement(self.caissier, vente.pk, "especes", Decimal("600"))
        self.assertEqual(vente.libelle_paiement, "Payée")

    def test_paiement_superieur_au_reste_refuse(self):
        vente = self.vendre(2, mode="mobile_money")
        with self.assertRaises(services.ErreurVente):
            services.ajouter_paiement(self.caissier, vente.pk, "especes", Decimal("1"))  # tout est déjà en attente

    def test_montant_invalide_refuse(self):
        vente = self.vendre(2, mode="mobile_money")
        for montant in (None, Decimal("0"), Decimal("-5")):
            with self.assertRaises(services.ErreurVente):
                services.ajouter_paiement(self.caissier, vente.pk, "especes", montant)

    def test_ajout_de_paiement_via_la_page(self):
        vente = self.vendre(2, mode="mobile_money")
        services.declarer_paiement_echoue(self.caissier, vente.paiements.get().pk)
        self.client.post(reverse("ventes:paiement_ajouter", args=[vente.pk]),
                         {"mode": "especes", "montant": "250,50", "reference": ""})
        self.assertEqual(vente.paiements.filter(statut="confirme").get().montant, Decimal("250.50"))


class HistoriqueEtPermissionsTests(CaisseTestCase):
    def test_liste_et_filtres(self):
        v1 = self.vendre(1, client=Client.objects.create(nom="Alice Test"))
        v2 = self.vendre(1)
        services.annuler_vente(self.caissier, v2.pk, "erreur")
        tous = self.client.get(reverse("ventes:liste"))
        par_client = self.client.get(reverse("ventes:liste"), {"q": "alice"})
        par_numero = self.client.get(reverse("ventes:liste"), {"q": v2.numero})
        annulees = self.client.get(reverse("ventes:liste"), {"statut": "annulee"})
        self.assertEqual(len(tous.context["page"]), 2)
        self.assertEqual([v.pk for v in par_client.context["page"]], [v1.pk])
        self.assertEqual([v.pk for v in par_numero.context["page"]], [v2.pk])
        self.assertEqual([v.pk for v in annulees.context["page"]], [v2.pk])

    def test_filtre_par_dates(self):
        self.vendre(1)
        demain = (self.aujourdhui + timedelta(days=1)).isoformat()
        hier = (self.aujourdhui - timedelta(days=1)).isoformat()
        self.assertEqual(len(self.client.get(reverse("ventes:liste"), {"du": demain}).context["page"]), 0)
        self.assertEqual(len(self.client.get(reverse("ventes:liste"), {"au": hier}).context["page"]), 0)
        self.assertEqual(len(self.client.get(reverse("ventes:liste"), {"du": hier, "au": demain}).context["page"]), 1)
        self.assertEqual(self.client.get(reverse("ventes:liste"), {"du": "n'importe quoi"}).status_code, 200)

    def test_recu_affiche(self):
        vente = self.vendre(3)
        r = self.client.get(reverse("ventes:detail", args=[vente.pk]))
        self.assertContains(r, vente.numero)
        self.assertContains(r, "1500")
        self.assertContains(r, "Paracétamol")

    def test_visiteur_anonyme(self):
        self.client.logout()
        for nom in ("ventes:caisse", "ventes:liste"):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 302)
        self.assertEqual(self.client.post(reverse("ventes:valider")).status_code, 302)

    def test_roles_sans_acces_a_la_caisse(self):
        for role in (roles.PHARMACIEN, roles.GESTIONNAIRE_STOCK, roles.RESPONSABLE_GESTION):
            self.client.force_login(creer_utilisateur(f"u_{role[:5]}", role))
            self.assertEqual(self.client.get(reverse("ventes:caisse")).status_code, 403, role)
            self.assertEqual(self.client.post(reverse("ventes:valider"), {"jeton": "x"}).status_code, 403, role)
        self.assertEqual(Vente.objects.count(), 0)

    def test_consultation_des_ventes_selon_les_roles(self):
        vente = self.vendre(1)
        for role, attendu in ((roles.PHARMACIEN, 200), (roles.RESPONSABLE_GESTION, 200), (roles.GESTIONNAIRE_STOCK, 403)):
            self.client.force_login(creer_utilisateur(f"v_{role[:5]}", role))
            self.assertEqual(self.client.get(reverse("ventes:liste")).status_code, attendu, role)
            self.assertEqual(self.client.get(reverse("ventes:detail", args=[vente.pk])).status_code, attendu, role)

    def test_responsable_de_gestion_ne_modifie_rien(self):
        vente = self.vendre(1, mode="mobile_money")
        self.client.force_login(creer_utilisateur("gestion", roles.RESPONSABLE_GESTION))
        p = vente.paiements.get()
        self.assertEqual(self.client.post(reverse("ventes:paiement_confirmer", args=[p.pk]), {"reference": "X"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("ventes:paiement_ajouter", args=[vente.pk])).status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.statut, Paiement.Statut.EN_ATTENTE)

    def test_actions_en_post_uniquement(self):
        for nom, args in (("ventes:valider", []), ("ventes:panier_vider", []), ("ventes:panier_retirer", [0])):
            self.assertEqual(self.client.get(reverse(nom, args=args)).status_code, 405, nom)
