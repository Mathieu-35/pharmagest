"""Calculs du tableau de bord et des rapports : tout est calculé à partir des données réelles.

Définitions (cahier des charges, 4.10) :
- Chiffre d'affaires (CA) : valeur des ventes validées de la période, nette des retours,
  au prix appliqué lors de la vente. Les ventes annulées sont exclues.
- Encaissements : paiements CONFIRMÉS reçus pendant la période (≠ CA).
- Marge commerciale brute : CA − coût d'achat des produits vendus. Ce n'est PAS un bénéfice net :
  les autres charges (salaires, loyer, taxes...) ne sont pas prises en compte.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from achats.models import CommandeAchat, ReceptionAchat
from medicaments.models import Medicament
from stock.models import LotStock
from stock.queries import avec_stock, en_rupture, sous_le_seuil
from ventes.models import LigneVente, Paiement, RetourVente, Vente

ZERO = Decimal("0")


def periode_par_defaut():
    """Du 1er du mois en cours à aujourd'hui."""
    aujourdhui = timezone.localdate()
    return aujourdhui.replace(day=1), aujourdhui


def _cout_unitaire(ligne):
    """Coût d'achat réel du lot (moyenne pondérée de ses réceptions) ; à défaut, le prix d'achat
    actuel du médicament."""
    receptions = list(ligne.lot.lignes_reception.all())
    quantite = sum(r.quantite for r in receptions)
    if quantite:
        return sum(r.quantite * r.ligne_achat.prix_achat for r in receptions) / quantite
    return ligne.medicament.prix_achat


def lignes_nettes(du, au):
    """Lignes des ventes validées de la période, avec quantité nette des retours."""
    lignes = (
        LigneVente.objects.filter(
            vente__statut=Vente.Statut.VALIDEE,
            vente__date__date__gte=du, vente__date__date__lte=au,
        )
        .select_related("vente", "medicament", "lot")
        .prefetch_related("lot__lignes_reception__ligne_achat")
        .annotate(retournee=Coalesce(Sum("retours__quantite"), 0))
    )
    resultat = []
    for ligne in lignes:
        nette = ligne.quantite - ligne.retournee
        resultat.append({
            "ligne": ligne, "quantite": nette,
            "ca": nette * ligne.prix_applique,
            "cout": nette * _cout_unitaire(ligne),
        })
    return resultat


def _somme(queryset, champ):
    return queryset.aggregate(t=Coalesce(Sum(champ), ZERO))["t"]


def statistiques_ventes(du, au, financieres=False):
    """Ventes de la période. Le coût et la marge ne sont calculés que si `financieres`."""
    lignes = lignes_nettes(du, au)
    ca = sum((l["ca"] for l in lignes), ZERO)

    par_jour = defaultdict(lambda: {"ventes": set(), "ca": ZERO})
    produits = defaultdict(lambda: {"quantite": 0, "ca": ZERO})
    for l in lignes:
        jour = timezone.localtime(l["ligne"].vente.date).date()
        par_jour[jour]["ventes"].add(l["ligne"].vente_id)
        par_jour[jour]["ca"] += l["ca"]
        medicament = l["ligne"].medicament
        produits[medicament]["quantite"] += l["quantite"]
        produits[medicament]["ca"] += l["ca"]

    nombre_ventes = Vente.objects.filter(
        statut=Vente.Statut.VALIDEE, date__date__gte=du, date__date__lte=au).count()
    resultat = {
        "du": du, "au": au,
        "nombre_ventes": nombre_ventes,
        "ca": ca,
        "par_jour": [
            {"jour": jour, "nombre": len(d["ventes"]), "ca": d["ca"]}
            for jour, d in sorted(par_jour.items())
        ],
        "produits_les_plus_vendus": [
            {"medicament": m, "quantite": d["quantite"], "ca": d["ca"]}
            for m, d in sorted(produits.items(), key=lambda x: (-x[1]["quantite"], x[0].nom_commercial))
            if d["quantite"] > 0
        ][:5],
    }
    if financieres:
        encaissements = Paiement.objects.filter(
            statut=Paiement.Statut.CONFIRME, date__date__gte=du, date__date__lte=au)
        cout = sum((l["cout"] for l in lignes), ZERO)
        resultat.update({
            "encaissements": _somme(encaissements, "montant"),
            "en_attente": _somme(Paiement.objects.filter(statut=Paiement.Statut.EN_ATTENTE), "montant"),
            "remboursements": _somme(
                RetourVente.objects.filter(date__date__gte=du, date__date__lte=au), "montant_rembourse"),
            "cout_achat": cout,
            "marge_brute": ca - cout,
        })
    return resultat


def ventes_du_jour():
    aujourdhui = timezone.localdate()
    lignes = lignes_nettes(aujourdhui, aujourdhui)
    return {
        "nombre": Vente.objects.filter(
            statut=Vente.Statut.VALIDEE, date__date=aujourdhui).count(),
        "ca": sum((l["ca"] for l in lignes), ZERO),
    }


def statistiques_achats(du, au):
    """Commandes passées (hors brouillons et annulées) et marchandises réceptionnées."""
    commandes = list(
        CommandeAchat.objects.filter(
            date_commande__date__gte=du, date_commande__date__lte=au,
        ).exclude(statut__in=[CommandeAchat.Statut.BROUILLON, CommandeAchat.Statut.ANNULEE])
        .select_related("fournisseur").prefetch_related("lignes")
    )
    receptions = list(
        ReceptionAchat.objects.filter(date_reception__date__gte=du, date_reception__date__lte=au)
        .select_related("commande__fournisseur").prefetch_related("lignes__ligne_achat")
    )
    return {
        "du": du, "au": au,
        "commandes": commandes,
        "nombre_commandes": len(commandes),
        "montant_commande": sum((c.montant_total for c in commandes), ZERO),
        "receptions": receptions,
        "montant_receptionne": sum((r.montant for r in receptions), ZERO),
    }


def jours_alerte():
    return settings.JOURS_ALERTE_PEREMPTION


def lots_proches_de_la_peremption():
    aujourdhui = timezone.localdate()
    return LotStock.objects.filter(
        quantite_restante__gt=0, date_peremption__gte=aujourdhui,
        date_peremption__lte=aujourdhui + timedelta(days=jours_alerte()),
    ).select_related("medicament").order_by("date_peremption", "id")


def lots_perimes_en_stock():
    return LotStock.objects.filter(
        quantite_restante__gt=0, date_peremption__lt=timezone.localdate(),
    ).select_related("medicament").order_by("date_peremption", "id")


def statistiques_stock():
    actifs = Medicament.objects.filter(statut=Medicament.Statut.ACTIF)
    avec = avec_stock(actifs)
    proches, perimes = lots_proches_de_la_peremption(), lots_perimes_en_stock()
    ruptures, faibles = en_rupture(avec), sous_le_seuil(avec)
    return {
        "medicaments_actifs": actifs.count(),
        "ruptures": ruptures.count(),
        "stocks_faibles": faibles.count(),
        "lots_proches": proches.count(),
        "lots_perimes": perimes.count(),
        "liste_ruptures": list(ruptures.order_by("nom_commercial")[:5]),
        "liste_faibles": list(faibles.order_by("nom_commercial")[:5]),
        "liste_proches": list(proches[:5]),
        "liste_perimes": list(perimes[:5]),
        "jours": jours_alerte(),
    }
