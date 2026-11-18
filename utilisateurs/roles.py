"""Rôles de PharmaGest (cahier des charges, section 3) = groupes Django + permissions.

Les groupes sont créés une seule fois après la migration. L'administrateur peut
ensuite ajuster leurs permissions dans l'administration Django.
"""

from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.apps import apps
from django.db import DEFAULT_DB_ALIAS

ADMINISTRATEUR = "Administrateur"
PHARMACIEN = "Pharmacien responsable"
GESTIONNAIRE_STOCK = "Gestionnaire de stock"
CAISSIER = "Caissier"
RESPONSABLE_GESTION = "Responsable de gestion"

TOUT = ["view", "add", "change", "delete"]
LECTURE = ["view"]
LECTURE_ECRITURE = ["view", "add", "change"]

APPLICATIONS = [
    "medicaments", "fournisseurs", "clients", "achats", "stock",
    "ventes", "utilisateurs", "rapports",
]

ACHATS = ["achats.commandeachat", "achats.ligneachat", "achats.receptionachat", "achats.lignereception"]
VENTES = ["ventes.vente", "ventes.lignevente", "ventes.paiement", "ventes.retourvente"]

# Permissions propres au tableau de bord et aux rapports (modèle « Rapport »)
TABLEAU = "voir_tableau_de_bord"
FINANCES = "voir_statistiques_financieres"
RAPPORTS = "generer_rapports"
CODENAMES_PERSONNALISES = {TABLEAU, FINANCES, RAPPORTS}

PERMISSIONS_PAR_ROLE = {
    # Contrôle les médicaments, lots, péremptions, achats et ventes
    PHARMACIEN: {
        "medicaments.medicament": TOUT,
        "medicaments.categorie": TOUT,
        "stock.lotstock": LECTURE_ECRITURE,
        "stock.mouvementstock": LECTURE,
        "fournisseurs.fournisseur": LECTURE,
        "clients.client": LECTURE,
        **{m: LECTURE for m in ACHATS},
        **{m: LECTURE for m in VENTES},
        "ventes.retourvente": ["view", "add"],
        "rapports.rapport": [TABLEAU, FINANCES, RAPPORTS],
    },
    # Gère fournisseurs, commandes, réceptions et inventaires
    GESTIONNAIRE_STOCK: {
        "fournisseurs.fournisseur": LECTURE_ECRITURE,
        **{m: LECTURE_ECRITURE for m in ACHATS},
        "stock.lotstock": LECTURE_ECRITURE,
        "stock.mouvementstock": ["view", "add"],
        "medicaments.medicament": LECTURE,
        "medicaments.categorie": LECTURE,
        "rapports.rapport": [TABLEAU, RAPPORTS],
    },
    # Enregistre les ventes, les paiements et imprime les reçus
    CAISSIER: {
        "ventes.vente": ["view", "add"],
        "ventes.lignevente": ["view", "add"],
        "ventes.paiement": LECTURE_ECRITURE,
        "clients.client": LECTURE_ECRITURE,
        "medicaments.medicament": LECTURE,
        "medicaments.categorie": LECTURE,
        "stock.lotstock": LECTURE,
        "rapports.rapport": [TABLEAU],
    },
    # Consulte les statistiques, les recettes et les rapports
    RESPONSABLE_GESTION: {
        "medicaments.medicament": LECTURE,
        "medicaments.categorie": LECTURE,
        "stock.lotstock": LECTURE,
        "stock.mouvementstock": LECTURE,
        "fournisseurs.fournisseur": LECTURE,
        "clients.client": LECTURE,
        **{m: LECTURE for m in ACHATS},
        **{m: LECTURE for m in VENTES},
        "rapports.rapport": [TABLEAU, FINANCES, RAPPORTS],
    },
}


def _permissions_administrateur(using):
    """Toutes les permissions de l'application et la gestion des comptes.
    Le journal d'audit reste en lecture seule (RG09)."""
    permissions = Permission.objects.using(using).filter(
        content_type__app_label__in=APPLICATIONS
    ) | Permission.objects.using(using).filter(
        content_type__app_label="auth", content_type__model__in=["user", "group"]
    )
    return permissions.exclude(
        content_type__app_label="utilisateurs",
        content_type__model="journalaudit",
        codename__in=["add_journalaudit", "change_journalaudit", "delete_journalaudit"],
    )


def _permissions(definition, using):
    trouvees = []
    for modele, actions in definition.items():
        app_label, nom_modele = modele.split(".")
        for action in actions:
            codename = action if action in CODENAMES_PERSONNALISES else f"{action}_{nom_modele}"
            trouvees.append(
                Permission.objects.using(using).get(
                    content_type__app_label=app_label, codename=codename,
                )
            )
    return trouvees


def creer_roles(sender=None, using=DEFAULT_DB_ALIAS, **kwargs):
    """Crée les groupes manquants avec leurs permissions (sans écraser les existants)."""
    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using)

    groupe, cree = Group.objects.using(using).get_or_create(name=ADMINISTRATEUR)
    if cree:
        groupe.permissions.set(_permissions_administrateur(using))

    for nom, definition in PERMISSIONS_PAR_ROLE.items():
        groupe, cree = Group.objects.using(using).get_or_create(name=nom)
        if cree:
            groupe.permissions.set(_permissions(definition, using))
