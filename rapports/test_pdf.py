from datetime import timedelta

from django.urls import reverse

from clients.models import Client
from rapports import pdf
from rapports.outils_tests import RapportsTestCase, texte_pdf
from stock.models import LotStock
from utilisateurs import roles
from utilisateurs.outils_tests import creer_utilisateur
from ventes import services


class DocumentsPdfTests(RapportsTestCase):
    def test_recu_pdf_lisible_avec_les_bons_totaux(self):
        vente = self.vendre(3)   # 3 × 500 = 1500
        contenu = pdf.recu_vente(vente)
        texte = texte_pdf(contenu)
        self.assertTrue(contenu.startswith(b"%PDF"))
        for attendu in (vente.numero, "Paracétamol", "1 500,00 Ar", "500,00 Ar", "Reçu de vente",
                        "PharmaGest", "caisse", "Vente comptoir", "Espèces"):
            self.assertIn(attendu, texte)
        self.assertIn(vente.date.astimezone().strftime("%d/%m/%Y"), texte)

    def test_recu_avec_plusieurs_lots_et_total_exact(self):
        vente = self.vendre(12)   # 10 du lot A + 2 du lot B = 6000
        texte = texte_pdf(pdf.recu_vente(vente))
        self.assertIn("6 000,00 Ar", texte)
        self.assertIn("A", texte)
        self.assertIn("B", texte)

    def test_recu_de_vente_annulee_et_remboursements(self):
        vente = self.vendre(2)
        services.annuler_vente(self.caissier, vente.pk, "erreur")
        vente.refresh_from_db()
        texte = texte_pdf(pdf.recu_vente(vente))
        self.assertIn("VENTE ANNUL", texte)
        self.assertIn("Total remboursé", texte)
        self.assertIn("1 000,00 Ar", texte)

    def test_recu_paiement_en_attente(self):
        vente = self.vendre(2, mode="mobile_money")
        texte = texte_pdf(pdf.recu_vente(vente))
        self.assertIn("En attente", texte)
        self.assertIn("Paiement en attente", texte)

    def test_facture_avec_client(self):
        client = Client.objects.create(nom="Alice Test", telephone="034 00 000 00", adresse="Lot 12 Tana")
        vente = self.vendre(2, client=client)
        texte = texte_pdf(pdf.facture_vente(vente))
        for attendu in (f"F-{vente.pk:06d}", "Facture", "Alice Test", "034 00 000 00", "Lot 12 Tana",
                        vente.numero, "1 000,00 Ar", "Total à payer"):
            self.assertIn(attendu, texte)

    def test_facture_client_comptoir(self):
        texte = texte_pdf(pdf.facture_vente(self.vendre(1)))
        self.assertIn("Client comptoir", texte)

    def test_bon_de_commande(self):
        commande, _ = self.receptionner(self.med, 10, "300")
        texte = texte_pdf(pdf.bon_commande(commande))
        for attendu in (commande.numero, "Bon de commande", "Grossiste Test", "Paracétamol",
                        "300,00 Ar", "3 000,00 Ar", "Total"):
            self.assertIn(attendu, texte)

    def test_bon_de_reception(self):
        commande, reception = self.receptionner(self.med, 10, "300", numero_lot="LOT-XYZ")
        texte = texte_pdf(pdf.bon_reception(reception))
        for attendu in (str(reception), "Bon de réception", commande.numero, "LOT-XYZ", "Paracétamol",
                        "3 000,00 Ar", "Grossiste Test", "caisse"):
            self.assertIn(attendu, texte)

    def test_informations_de_la_pharmacie_et_mentions(self):
        infos = {"nom": "Pharmacie Test", "adresse": "Rue des Tests, Antananarivo", "telephone": "020 22 000 00",
                 "email": "p@example.com", "numero_fiscal": "NIF-123", "mentions_legales": "Mention de test"}
        with self.settings(PHARMACIE=infos):
            texte = texte_pdf(pdf.recu_vente(self.vendre(1)))
        for valeur in ("Pharmacie Test", "Rue des Tests, Antananarivo", "020 22 000 00", "NIF-123", "Mention de test"):
            self.assertIn(valeur, texte)

    def test_devise_configurable(self):
        with self.settings(DEVISE="EUR"):
            self.assertIn("1 000,00 EUR", texte_pdf(pdf.recu_vente(self.vendre(2))))

    def test_caracteres_speciaux_ne_cassent_pas_le_pdf(self):
        self.med.nom_commercial = "Doli & <b>Co</b> «test»"
        self.med.save()
        client = Client.objects.create(nom="O'Brien & Fils <x>")
        contenu = pdf.facture_vente(self.vendre(1, client=client))
        self.assertTrue(contenu.startswith(b"%PDF"))
        texte = texte_pdf(contenu)
        self.assertIn("Doli &", texte)
        self.assertIn("Fils", texte)

    def test_montants_formates(self):
        from decimal import Decimal
        self.assertEqual(pdf.montant(Decimal("1234567.5")), "1 234 567,50 Ar")
        self.assertEqual(pdf.montant(0), "0,00 Ar")
        self.assertEqual(pdf.montant(None), "0,00 Ar")


class RapportsPdfTests(RapportsTestCase):
    def test_rapport_de_stock(self):
        LotStock.objects.create(medicament=self.med, numero_lot="PER", quantite_recue=4, quantite_restante=4,
                                date_peremption=self.aujourdhui - timedelta(days=1))
        texte = texte_pdf(pdf.rapport_stock())
        for attendu in ("Rapport de stock", "Paracétamol", "20", "Normal", "Bloqué", "Disponible"):
            self.assertIn(attendu, texte)

    def test_rapport_de_stock_etats(self):
        self.autre_medicament("Vide")
        bas = self.autre_medicament("Bas", seuil_alerte=10)
        self.creer_lot(bas, "B", quantite=3)
        texte = texte_pdf(pdf.rapport_stock())
        self.assertIn("Rupture", texte)
        self.assertIn("Stock faible", texte)

    def test_rapport_des_ventes_avec_synthese(self):
        v1 = self.vendre(2)                          # 1000 encaissé
        self.vendre(4, mode="mobile_money")          # 2000 en attente
        texte = texte_pdf(pdf.rapport_ventes(self.aujourdhui, self.aujourdhui))
        for attendu in ("Rapport des ventes", v1.numero, "3 000,00 Ar", "1 000,00 Ar", "2 000,00 Ar",
                        "Chiffre d'affaires", "Encaissements", "Marge commerciale brute", "bénéfice net"):
            self.assertIn(attendu, texte)

    def test_rapport_des_achats(self):
        commande, reception = self.receptionner(self.med, 10, "300")
        texte = texte_pdf(pdf.rapport_achats(self.aujourdhui, self.aujourdhui))
        for attendu in ("Rapport des achats", commande.numero, str(reception), "3 000,00 Ar", "Grossiste Test"):
            self.assertIn(attendu, texte)

    def test_rapport_des_peremptions(self):
        LotStock.objects.create(medicament=self.med, numero_lot="VIEUX", quantite_recue=4, quantite_restante=4,
                                date_peremption=self.aujourdhui - timedelta(days=5))
        texte = texte_pdf(pdf.rapport_peremptions())
        for attendu in ("Produits proches de la", "VIEUX", "Paracétamol", "A"):
            self.assertIn(attendu, texte)
        self.assertIn("Lots périmés", texte)

    def test_rapports_sans_donnees_ne_plantent_pas(self):
        LotStock.objects.all().delete()
        for contenu in (pdf.rapport_stock(), pdf.rapport_ventes(self.aujourdhui, self.aujourdhui),
                        pdf.rapport_achats(self.aujourdhui, self.aujourdhui), pdf.rapport_peremptions()):
            self.assertTrue(contenu.startswith(b"%PDF"))

    def test_rapport_volumineux_sur_plusieurs_pages(self):
        for i in range(120):
            self.autre_medicament(f"Médicament numéro {i:03d}")
        contenu = pdf.rapport_stock()
        self.assertGreater(contenu.count(b"/Type /Page\n"), 1)
        self.assertIn("Page 2", texte_pdf(contenu))


class VuesPdfTests(RapportsTestCase):
    def setUp(self):
        super().setUp()
        self.vente = self.vendre(3)
        self.commande, self.reception = self.receptionner(self.med, 10, "300")

    def urls_documents(self):
        return {
            "recu": reverse("rapports:recu", args=[self.vente.pk]),
            "facture": reverse("rapports:facture", args=[self.vente.pk]),
            "bon_commande": reverse("rapports:bon_commande", args=[self.commande.pk]),
            "bon_reception": reverse("rapports:bon_reception", args=[self.reception.pk]),
        }

    def urls_rapports(self):
        return {nom: reverse(f"rapports:{nom}") for nom in ("stock", "ventes", "achats", "peremptions")}

    def test_reponses_pdf(self):
        self.client.force_login(creer_utilisateur("admin_test", roles.ADMINISTRATEUR))
        for url in [*self.urls_documents().values(), *self.urls_rapports().values()]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r["Content-Type"], "application/pdf")
                self.assertTrue(r.content.startswith(b"%PDF"))
                self.assertIn("inline", r["Content-Disposition"])

    def test_recu_via_la_vue_contient_le_bon_total(self):
        r = self.client.get(reverse("rapports:recu", args=[self.vente.pk]))   # caissier
        self.assertEqual(r.status_code, 200)
        self.assertIn("1 500,00 Ar", texte_pdf(r.content))
        self.assertIn("recu-V-", r["Content-Disposition"])

    def test_periode_passee_en_parametre(self):
        self.client.force_login(creer_utilisateur("gestion", roles.RESPONSABLE_GESTION))
        r = self.client.get(reverse("rapports:ventes"), {"du": "2000-01-01", "au": "2000-01-31"})
        self.assertIn("du 01/01/2000 au 31/01/2000", texte_pdf(r.content))
        self.assertNotIn(self.vente.numero, texte_pdf(r.content))

    def test_documents_inexistants(self):
        self.assertEqual(self.client.get(reverse("rapports:recu", args=[9999])).status_code, 404)

    def test_visiteur_anonyme(self):
        self.client.logout()
        for url in [*self.urls_documents().values(), *self.urls_rapports().values(), reverse("rapports:liste")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_caissier_recus_et_factures_seulement(self):
        docs, rapports = self.urls_documents(), self.urls_rapports()
        self.assertEqual(self.client.get(docs["recu"]).status_code, 200)
        self.assertEqual(self.client.get(docs["facture"]).status_code, 200)
        self.assertEqual(self.client.get(docs["bon_commande"]).status_code, 403)
        self.assertEqual(self.client.get(docs["bon_reception"]).status_code, 403)
        for url in rapports.values():
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse("rapports:liste")).status_code, 403)

    def test_gestionnaire_de_stock_rapports_de_stock_et_achats_pas_de_ventes(self):
        self.client.force_login(creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK))
        docs, rapports = self.urls_documents(), self.urls_rapports()
        for nom in ("stock", "achats", "peremptions"):
            self.assertEqual(self.client.get(rapports[nom]).status_code, 200, nom)
        self.assertEqual(self.client.get(rapports["ventes"]).status_code, 403)
        self.assertEqual(self.client.get(docs["bon_commande"]).status_code, 200)
        self.assertEqual(self.client.get(docs["bon_reception"]).status_code, 200)
        self.assertEqual(self.client.get(docs["recu"]).status_code, 403)

    def test_responsable_de_gestion_tous_les_rapports(self):
        self.client.force_login(creer_utilisateur("gestion", roles.RESPONSABLE_GESTION))
        for url in self.urls_rapports().values():
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_pharmacien_tous_les_rapports_et_documents(self):
        self.client.force_login(creer_utilisateur("pharma", roles.PHARMACIEN))
        for url in [*self.urls_documents().values(), *self.urls_rapports().values()]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_page_liste_des_rapports_selon_le_role(self):
        self.client.force_login(creer_utilisateur("stock", roles.GESTIONNAIRE_STOCK))
        r = self.client.get(reverse("rapports:liste"))
        self.assertContains(r, "Rapport de stock")
        self.assertContains(r, "Rapport des achats")
        self.assertNotContains(r, "Rapport des ventes")
        self.client.force_login(creer_utilisateur("gestion", roles.RESPONSABLE_GESTION))
        self.assertContains(self.client.get(reverse("rapports:liste")), "Rapport des ventes")

    def test_liens_pdf_sur_les_pages_de_vente_et_de_commande(self):
        self.client.force_login(creer_utilisateur("admin_test", roles.ADMINISTRATEUR))
        page = self.client.get(reverse("ventes:detail", args=[self.vente.pk]))
        self.assertContains(page, reverse("rapports:recu", args=[self.vente.pk]))
        self.assertContains(page, reverse("rapports:facture", args=[self.vente.pk]))
        page = self.client.get(reverse("achats:detail", args=[self.commande.pk]))
        self.assertContains(page, reverse("rapports:bon_commande", args=[self.commande.pk]))
        self.assertContains(page, reverse("rapports:bon_reception", args=[self.reception.pk]))
