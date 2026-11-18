"""Opérations métier des ventes.

Règles appliquées ici :
- RG06 / RG07 : la sortie de stock se fait une seule fois, dans la même transaction que
  la vente, et le stock ne peut pas devenir négatif (décrément conditionnel en base).
- RG08 : seuls les lots non périmés et non bloqués sont vendables ; méthode FEFO.
- RG12 : le prix appliqué est figé dans la ligne de vente.
- Anti double validation : jeton unique par vente.
- Retours et annulations : opérations compensatoires, jamais une suppression.
"""

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from config.concurrence import reessayer_si_conflit
from medicaments.models import Medicament
from stock.models import LotStock, MouvementStock
from utilisateurs import audit

from .models import LigneVente, Paiement, RetourVente, Vente


class ErreurVente(Exception):
    """Opération refusée ; le message est affichable à l'utilisateur."""


# ------------------------------------------------------------------ Stock vendable

def lots_vendables(medicament, lot_id=None):
    """Lots délivrables, dans l'ordre FEFO (péremption la plus proche d'abord)."""
    lots = LotStock.objects.filter(
        medicament=medicament, bloque=False,
        date_peremption__gte=timezone.localdate(), quantite_restante__gt=0,
    )
    if lot_id:
        lots = lots.filter(pk=lot_id)
    return lots.order_by("date_peremption", "id")


def stock_vendable(medicament, lot_id=None):
    return lots_vendables(medicament, lot_id).aggregate(t=Sum("quantite_restante"))["t"] or 0


def allouer(medicament, quantite, lot_id=None, verrouiller=False):
    """Répartit une quantité sur les lots selon la méthode FEFO.
    Retourne [(lot, quantité)]. Refuse une quantité nulle, négative ou supérieure au stock."""
    if quantite < 1:
        raise ErreurVente("La quantité doit être d'au moins 1.")
    lots = lots_vendables(medicament, lot_id)
    if verrouiller:
        lots = lots.select_for_update()
    restant, repartition = quantite, []
    for lot in lots:
        pris = min(lot.quantite_restante, restant)
        repartition.append((lot, pris))
        restant -= pris
        if restant == 0:
            return repartition
    disponible = quantite - restant
    raise ErreurVente(
        f"Stock insuffisant pour {medicament} : {quantite} demandé(s), "
        f"{disponible} disponible(s) à la vente."
    )


def _sortir(lot_id, quantite):
    """Décrément conditionnel : n'aboutit que si le stock suffit et que le lot est encore
    vendable. Deux validations simultanées ne peuvent donc pas rendre le stock négatif."""
    modifies = LotStock.objects.filter(
        pk=lot_id, quantite_restante__gte=quantite, bloque=False,
        date_peremption__gte=timezone.localdate(),
    ).update(quantite_restante=F("quantite_restante") - quantite)
    if not modifies:
        raise ErreurVente("Le stock a changé pendant la validation : vérifiez le panier et recommencez.")


# ------------------------------------------------------------------------- Vente

class _DejaValidee(Exception):
    def __init__(self, vente):
        self.vente = vente


def valider_vente(utilisateur, lignes, mode, jeton, client=None):
    """Valide une vente. `lignes` : [{medicament_id, quantite, lot_id}].
    Retourne (vente, creee). Rejouer le même jeton ne refait aucune sortie de stock."""
    try:
        return reessayer_si_conflit(
            lambda: _valider_vente(utilisateur, lignes, mode, jeton, client)), True
    except _DejaValidee as deja:
        return deja.vente, False
    except (IntegrityError, OperationalError) as erreur:
        # Deux validations simultanées : l'une a gagné, l'autre est refusée proprement
        existante = Vente.objects.filter(jeton=jeton).first()
        if existante:
            return existante, False
        if isinstance(erreur, OperationalError):
            raise ErreurVente("Une autre opération est en cours : réessayez dans un instant.")
        raise


@transaction.atomic
def _valider_vente(utilisateur, lignes, mode, jeton, client):
    existante = Vente.objects.filter(jeton=jeton).first()
    if existante:
        raise _DejaValidee(existante)
    if not lignes:
        raise ErreurVente("Le panier est vide.")
    if mode not in Paiement.Mode.values:
        raise ErreurVente("Choisissez un mode de paiement.")
    if client is not None and not client.actif:
        raise ErreurVente("Ce client est inactif.")

    vente = Vente.objects.create(client=client, vendeur=utilisateur, jeton=jeton)

    for ligne in lignes:
        try:
            medicament = Medicament.objects.get(pk=ligne["medicament_id"])
        except Medicament.DoesNotExist:
            raise ErreurVente("Un médicament du panier n'existe plus.")
        if not medicament.est_actif:
            raise ErreurVente(f"{medicament} est archivé : il ne peut plus être vendu.")
        for lot, quantite in allouer(
            medicament, int(ligne["quantite"]), ligne.get("lot_id"), verrouiller=True
        ):
            _sortir(lot.pk, quantite)
            LigneVente.objects.create(
                vente=vente, medicament=medicament, lot=lot, quantite=quantite,
                prix_applique=medicament.prix_vente,  # RG12 : prix figé
            )
            MouvementStock.objects.create(
                lot=lot, type=MouvementStock.Type.SORTIE, quantite=quantite,
                motif=f"Vente {vente.numero}", utilisateur=utilisateur,
            )

    total = vente.total
    if total > 0:
        Paiement.objects.create(
            vente=vente, mode=mode, montant=total, statut=_statut_initial(mode),
        )
    audit.enregistrer(utilisateur, "Vente enregistrée", vente, f"Total : {total}")
    return vente


def _statut_initial(mode):
    """Seul l'encaissement en espèces est immédiatement confirmé ; un paiement
    électronique reste en attente jusqu'à vérification de son statut."""
    return Paiement.Statut.CONFIRME if mode == Paiement.Mode.ESPECES else Paiement.Statut.EN_ATTENTE


# --------------------------------------------------------------------- Paiements

@transaction.atomic
def ajouter_paiement(utilisateur, vente_id, mode, montant, reference=""):
    vente = Vente.objects.select_for_update().get(pk=vente_id)
    if vente.statut == Vente.Statut.ANNULEE:
        raise ErreurVente("Cette vente est annulée.")
    if mode not in Paiement.Mode.values:
        raise ErreurVente("Choisissez un mode de paiement.")
    if montant is None or montant <= 0:
        raise ErreurVente("Le montant doit être positif.")
    if montant > vente.reste_a_payer:
        raise ErreurVente(f"Le montant dépasse le reste à payer ({vente.reste_a_payer}).")
    paiement = Paiement.objects.create(
        vente=vente, mode=mode, montant=montant, statut=_statut_initial(mode),
        reference_transaction=(reference or "").strip(),
    )
    audit.enregistrer(utilisateur, "Paiement ajouté", vente, f"{paiement}")
    return paiement


@transaction.atomic
def confirmer_paiement(utilisateur, paiement_id, reference=""):
    paiement = Paiement.objects.select_for_update().select_related("vente").get(pk=paiement_id)
    if paiement.vente.statut == Vente.Statut.ANNULEE:
        raise ErreurVente("Cette vente est annulée.")
    if paiement.statut != Paiement.Statut.EN_ATTENTE:
        raise ErreurVente("Seul un paiement en attente peut être confirmé.")
    reference = (reference or "").strip() or paiement.reference_transaction
    if paiement.mode != Paiement.Mode.ESPECES and not reference:
        raise ErreurVente("Saisissez la référence de la transaction après l'avoir vérifiée.")
    paiement.statut = Paiement.Statut.CONFIRME
    paiement.reference_transaction = reference
    paiement.save(update_fields=["statut", "reference_transaction"])
    audit.enregistrer(utilisateur, "Paiement confirmé", paiement.vente, f"{paiement} — réf. {reference}")
    return paiement


@transaction.atomic
def declarer_paiement_echoue(utilisateur, paiement_id):
    paiement = Paiement.objects.select_for_update().select_related("vente").get(pk=paiement_id)
    if paiement.statut != Paiement.Statut.EN_ATTENTE:
        raise ErreurVente("Seul un paiement en attente peut être déclaré échoué.")
    paiement.statut = Paiement.Statut.ECHOUE
    paiement.save(update_fields=["statut"])
    audit.enregistrer(utilisateur, "Paiement échoué", paiement.vente, f"{paiement}")
    return paiement


# ----------------------------------------------------------- Retours et annulations

def _verifier_eligible(lot):
    if lot.bloque or lot.est_perime:
        raise ErreurVente(
            f"Le lot {lot.numero_lot} est périmé ou bloqué : la remise en stock est interdite."
        )


def _remettre_en_stock(lot_id, quantite, vente, motif, utilisateur):
    lot = LotStock.objects.select_for_update().get(pk=lot_id)
    _verifier_eligible(lot)
    modifies = LotStock.objects.filter(
        pk=lot_id, quantite_restante__lte=F("quantite_recue") - quantite
    ).update(quantite_restante=F("quantite_restante") + quantite)
    if not modifies:
        raise ErreurVente(
            f"Remise en stock impossible : le lot {lot.numero_lot} dépasserait sa quantité reçue."
        )
    MouvementStock.objects.create(
        lot=lot, type=MouvementStock.Type.RETOUR, quantite=quantite,
        motif=f"Retour sur {vente.numero} — {motif}"[:255], utilisateur=utilisateur,
    )


def _creer_retour(utilisateur, vente, ligne, quantite, motif, remettre_en_stock):
    if remettre_en_stock:
        _remettre_en_stock(ligne.lot_id, quantite, vente, motif, utilisateur)
    return RetourVente.objects.create(
        ligne_vente=ligne, quantite=quantite, motif=motif,
        remis_en_stock=remettre_en_stock, enregistre_par=utilisateur,
        montant_rembourse=quantite * ligne.prix_applique,
    )


@transaction.atomic
def retourner(utilisateur, vente_id, retours, motif):
    """Enregistre des retours. `retours` : [{ligne_id, quantite, remettre_en_stock}].
    La vente d'origine est conservée ; le remboursement est calculé au prix appliqué."""
    motif = (motif or "").strip()
    if not motif:
        raise ErreurVente("Indiquez le motif du retour.")
    vente = Vente.objects.select_for_update().get(pk=vente_id)
    if vente.statut == Vente.Statut.ANNULEE:
        raise ErreurVente("Cette vente est annulée : tout a déjà été retourné.")
    lignes = {
        l.pk: l for l in LigneVente.objects.select_for_update().select_related("lot", "medicament")
        .filter(vente=vente)
    }
    crees = []
    for retour in retours:
        ligne = lignes.get(retour["ligne_id"])
        if ligne is None:
            raise ErreurVente("Une ligne ne fait pas partie de cette vente.")
        quantite = retour["quantite"]
        if quantite < 1:
            raise ErreurVente("La quantité retournée doit être d'au moins 1.")
        if quantite > ligne.quantite_retournable:
            raise ErreurVente(
                f"{ligne.medicament} : {quantite} retourné(s) mais seulement "
                f"{ligne.quantite_retournable} peuvent encore l'être."
            )
        crees.append(_creer_retour(
            utilisateur, vente, ligne, quantite, motif, retour.get("remettre_en_stock", False)))
    if not crees:
        raise ErreurVente("Indiquez au moins une quantité à retourner.")
    montant = sum(r.montant_rembourse for r in crees)
    audit.enregistrer(utilisateur, "Retour enregistré", vente, f"Remboursement : {montant} — {motif}")
    return crees


@transaction.atomic
def annuler_vente(utilisateur, vente_id, motif, remettre_en_stock=True):
    """Annule une vente par opération compensatoire : tout ce qui n'a pas encore été retourné
    est retourné. Les produits ne sont remis en stock que si leur lot est éligible.
    Retourne (vente, nombre de lignes non remises en stock)."""
    motif = (motif or "").strip()
    if not motif:
        raise ErreurVente("Indiquez le motif de l'annulation.")
    vente = Vente.objects.select_for_update().get(pk=vente_id)
    if vente.statut == Vente.Statut.ANNULEE:
        raise ErreurVente("Cette vente est déjà annulée.")

    non_remises = 0
    for ligne in LigneVente.objects.select_for_update().select_related("lot").filter(vente=vente):
        reste = ligne.quantite_retournable
        if reste < 1:
            continue
        eligible = not (ligne.lot.bloque or ligne.lot.est_perime)
        remettre = remettre_en_stock and eligible
        if remettre_en_stock and not eligible:
            non_remises += 1
        _creer_retour(utilisateur, vente, ligne, reste, f"Annulation : {motif}", remettre)

    for paiement in vente.paiements.filter(statut=Paiement.Statut.EN_ATTENTE):
        paiement.statut = Paiement.Statut.ECHOUE
        paiement.save(update_fields=["statut"])

    vente.statut = Vente.Statut.ANNULEE
    vente.save(update_fields=["statut"])
    audit.enregistrer(utilisateur, "Vente annulée", vente, motif)
    return vente, non_remises
