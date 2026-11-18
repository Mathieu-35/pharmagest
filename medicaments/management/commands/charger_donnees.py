"""Charge un jeu de données fictives (aucune donnée réelle).

Usage : python manage.py charger_donnees
Peut être relancée sans créer de doublons. Les dates des lots sont calculées
par rapport à aujourd'hui pour montrer les alertes de péremption.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from clients.models import Client
from fournisseurs.models import Fournisseur
from medicaments.models import Categorie, Medicament
from stock.models import LotStock, MouvementStock

CATEGORIES = {
    "Antalgiques": "Médicaments contre la douleur et la fièvre",
    "Antibiotiques": "Traitement des infections bactériennes",
    "Vitamines": "Compléments vitaminiques",
    "Antiseptiques": "Désinfection de la peau et des plaies",
    "Sirops": "Sirops et solutions buvables",
}

# (nom, générique, catégorie, forme, dosage, labo, code-barres, achat, vente, seuil)
MEDICAMENTS = [
    ("Paracétamol", "Paracétamol", "Antalgiques", "comprime", "500 mg", "Labo Test A", "3400000000011", "300", "500", 50),
    ("Ibuprofène", "Ibuprofène", "Antalgiques", "comprime", "400 mg", "Labo Test A", "3400000000028", "450", "700", 30),
    ("Amoxicilline", "Amoxicilline", "Antibiotiques", "gelule", "500 mg", "Labo Test B", "3400000000035", "900", "1400", 20),
    ("Vitamine C", "Acide ascorbique", "Vitamines", "comprime", "500 mg", "Labo Test C", "3400000000042", "600", "1000", 25),
    ("Antiseptique cutané", "Chlorhexidine", "Antiseptiques", "solution", "250 ml", "Labo Test C", "3400000000059", "2500", "3800", 10),
    ("Sirop contre la toux", "", "Sirops", "sirop", "120 ml", "Labo Test B", None, "2000", "3200", 15),
]

FOURNISSEURS = [
    ("Grossiste Test Antananarivo", "Lot 1 Antananarivo", "020 00 000 01", "contact@grossiste-test.example", "NIF-TEST-001", "M. Rakoto"),
    ("Distribution Pharma Test", "Lot 2 Toamasina", "020 00 000 02", "info@distribution-test.example", "NIF-TEST-002", "Mme Rasoa"),
]

CLIENTS = [
    ("Client Test Un", "034 00 000 01"),
    ("Client Test Deux", "033 00 000 02"),
]


class Command(BaseCommand):
    help = "Charge un jeu de données fictives pour les tests et la démonstration."

    @transaction.atomic
    def handle(self, *args, **options):
        aujourdhui = timezone.localdate()
        categories = {
            nom: Categorie.objects.get_or_create(nom=nom, defaults={"description": desc})[0]
            for nom, desc in CATEGORIES.items()
        }

        medicaments = {}
        for nom, gen, cat, forme, dosage, labo, code, achat, vente, seuil in MEDICAMENTS:
            medicaments[nom] = Medicament.objects.get_or_create(
                nom_commercial=nom,
                dosage=dosage,
                defaults={
                    "denomination_generique": gen,
                    "categorie": categories[cat],
                    "forme": forme,
                    "laboratoire": labo,
                    "code_barres": code,
                    "prix_achat": Decimal(achat),
                    "prix_vente": Decimal(vente),
                    "seuil_alerte": seuil,
                },
            )[0]

        for nom, adresse, tel, email, nif, contact in FOURNISSEURS:
            Fournisseur.objects.get_or_create(
                nom=nom,
                defaults={
                    "adresse": adresse, "telephone": tel, "email": email,
                    "numero_fiscal": nif, "contact_principal": contact,
                },
            )
        for nom, tel in CLIENTS:
            Client.objects.get_or_create(nom=nom, defaults={"telephone": tel})

        # (médicament, n° lot, jours avant péremption, quantité, bloqué)
        lots = [
            ("Paracétamol", "PARA-001", 365, 100, False),
            ("Paracétamol", "PARA-002", 25, 40, False),     # péremption proche
            ("Ibuprofène", "IBU-001", 300, 60, False),
            ("Amoxicilline", "AMOX-001", -30, 30, False),   # périmé
            ("Vitamine C", "VITC-001", 200, 80, False),
            ("Antiseptique cutané", "ANTI-001", 150, 5, True),  # bloqué
            ("Sirop contre la toux", "SIRO-001", 180, 12, False),  # sous le seuil
        ]
        for nom, numero, jours, quantite, bloque in lots:
            lot, cree = LotStock.objects.get_or_create(
                medicament=medicaments[nom],
                numero_lot=numero,
                defaults={
                    "date_peremption": aujourdhui + timedelta(days=jours),
                    "quantite_recue": quantite,
                    "quantite_restante": quantite,
                    "bloque": bloque,
                },
            )
            if cree:
                MouvementStock.objects.create(
                    lot=lot,
                    type=MouvementStock.Type.ENTREE,
                    quantite=quantite,
                    motif="Stock initial (données fictives)",
                )

        self.stdout.write(self.style.SUCCESS(
            f"{Categorie.objects.count()} catégories, {Medicament.objects.count()} médicaments, "
            f"{LotStock.objects.count()} lots, {Fournisseur.objects.count()} fournisseurs, "
            f"{Client.objects.count()} clients."
        ))
