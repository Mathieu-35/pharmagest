"""Opérations de stock traçables : chaque modification de quantité crée un mouvement."""

from django.db import transaction

from utilisateurs import audit

from .models import LotStock, MouvementStock


class ErreurStock(Exception):
    """Opération de stock refusée ; le message est affichable à l'utilisateur."""


@transaction.atomic
def basculer_blocage(lot_id, utilisateur):
    """Bloque un lot (retiré de la vente, RG08) ou le débloque."""
    lot = LotStock.objects.select_for_update().get(pk=lot_id)
    lot.bloque = not lot.bloque
    lot.save(update_fields=["bloque"])
    audit.enregistrer(
        utilisateur, "Lot bloqué" if lot.bloque else "Lot débloqué", lot,
    )
    return lot


@transaction.atomic
def corriger_inventaire(utilisateur, comptages, motif):
    """Applique les quantités comptées lors d'un inventaire physique.

    `comptages` : {lot_id: quantité comptée}. Seuls les lots dont la quantité diffère
    sont corrigés, avec un mouvement « correction » portant l'ancienne et la nouvelle
    quantité. Retourne le nombre de lots corrigés.
    """
    motif = (motif or "").strip()
    if not motif:
        raise ErreurStock("Indiquez le motif de l'inventaire.")

    lots = LotStock.objects.select_for_update().filter(pk__in=comptages.keys())
    corriges = 0
    for lot in lots:
        compte = comptages[lot.pk]
        if compte < 0:
            raise ErreurStock(f"{lot} : la quantité comptée ne peut pas être négative.")
        if compte > lot.quantite_recue:
            raise ErreurStock(
                f"{lot} : {compte} compté(s) dépasse la quantité reçue ({lot.quantite_recue})."
            )
        if compte == lot.quantite_restante:
            continue
        ecart = compte - lot.quantite_restante
        MouvementStock.objects.create(
            lot=lot,
            type=MouvementStock.Type.CORRECTION,
            quantite=abs(ecart),
            motif=f"{motif} : {lot.quantite_restante} → {compte} ({ecart:+d})"[:255],
            utilisateur=utilisateur,
        )
        lot.quantite_restante = compte
        lot.save(update_fields=["quantite_restante"])
        corriges += 1

    audit.enregistrer(
        utilisateur, "Inventaire enregistré", f"{corriges} correction(s)", motif
    )
    return corriges
