"""Opérations métier des achats.

Une commande ne modifie jamais le stock (RG04). Seule la réception l'augmente,
une seule fois (RG05), dans une transaction, avec un mouvement de stock traçable.
"""

from django.db import IntegrityError, OperationalError, transaction

from stock.models import LotStock, MouvementStock
from utilisateurs import audit

from .models import CommandeAchat, LigneAchat, LigneReception, ReceptionAchat


class ErreurAchat(Exception):
    """Opération d'achat refusée ; le message est affichable à l'utilisateur."""


def _verrouiller(commande_id):
    return CommandeAchat.objects.select_for_update().get(pk=commande_id)


@transaction.atomic
def valider_commande(commande_id, utilisateur):
    commande = _verrouiller(commande_id)
    if commande.statut != CommandeAchat.Statut.BROUILLON:
        raise ErreurAchat("Seule une commande en brouillon peut être validée.")
    if not commande.lignes.exists():
        raise ErreurAchat("La commande ne contient aucun médicament.")
    commande.statut = CommandeAchat.Statut.COMMANDEE
    commande.save(update_fields=["statut"])
    audit.enregistrer(utilisateur, "Commande validée", commande, f"Montant : {commande.montant_total}")
    return commande


@transaction.atomic
def annuler_commande(commande_id, utilisateur):
    commande = _verrouiller(commande_id)
    if not commande.est_annulable:
        raise ErreurAchat("Cette commande ne peut plus être annulée (déjà réceptionnée en tout ou partie).")
    commande.statut = CommandeAchat.Statut.ANNULEE
    commande.save(update_fields=["statut"])
    audit.enregistrer(utilisateur, "Commande annulée", commande)
    return commande


def receptionner(commande_id, utilisateur, jeton, saisies):
    """Enregistre une réception totale ou partielle.

    `saisies` : liste de dicts {ligne_id, quantite, numero_lot, date_peremption}.
    Retourne (reception, creee). Si le même jeton est rejoué, rien n'est ajouté
    et la réception déjà enregistrée est renvoyée avec creee=False.
    """
    try:
        return _receptionner(commande_id, utilisateur, jeton, saisies), True
    except _DejaEnregistree as deja:
        return deja.reception, False
    except (IntegrityError, OperationalError) as erreur:
        # Deux envois simultanés du même formulaire : l'un des deux a déjà gagné
        existante = jeton and ReceptionAchat.objects.filter(jeton=jeton).first()
        if existante:
            return existante, False
        if isinstance(erreur, OperationalError):
            raise ErreurAchat("Une autre opération est en cours : réessayez dans un instant.")
        raise


class _DejaEnregistree(Exception):
    def __init__(self, reception):
        self.reception = reception


@transaction.atomic
def _receptionner(commande_id, utilisateur, jeton, saisies):
    commande = _verrouiller(commande_id)

    if jeton:
        existante = ReceptionAchat.objects.filter(jeton=jeton).first()
        if existante:
            raise _DejaEnregistree(existante)

    if not commande.est_receptionnable:
        raise ErreurAchat("Cette commande n'est pas réceptionnable (validez-la d'abord, ou elle est terminée ou annulée).")
    if not saisies:
        raise ErreurAchat("Aucune quantité reçue.")

    reception = ReceptionAchat.objects.create(
        commande=commande, recue_par=utilisateur, jeton=jeton
    )

    for saisie in saisies:
        try:
            ligne = commande.lignes.select_for_update().get(pk=saisie["ligne_id"])
        except LigneAchat.DoesNotExist:
            raise ErreurAchat("Une ligne ne fait pas partie de cette commande.")

        quantite = saisie["quantite"]
        if quantite < 1:
            raise ErreurAchat("Une quantité reçue doit être positive.")
        if quantite > ligne.quantite_a_recevoir:
            raise ErreurAchat(
                f"{ligne.medicament} : {quantite} reçu(s) mais il n'en reste que "
                f"{ligne.quantite_a_recevoir} à recevoir."
            )

        lot = (
            LotStock.objects.select_for_update()
            .filter(medicament=ligne.medicament, numero_lot=saisie["numero_lot"])
            .first()
        )
        if lot is None:
            lot = LotStock.objects.create(
                medicament=ligne.medicament,
                numero_lot=saisie["numero_lot"],
                date_peremption=saisie["date_peremption"],
                quantite_recue=quantite,
                quantite_restante=quantite,
            )
        else:
            if lot.date_peremption != saisie["date_peremption"]:
                raise ErreurAchat(
                    f"Le lot {lot.numero_lot} de {ligne.medicament} existe déjà avec une autre "
                    f"date de péremption ({lot.date_peremption:%d/%m/%Y})."
                )
            lot.quantite_recue += quantite
            lot.quantite_restante += quantite
            lot.save(update_fields=["quantite_recue", "quantite_restante"])

        LigneReception.objects.create(
            reception=reception, ligne_achat=ligne, lot=lot, quantite=quantite
        )
        MouvementStock.objects.create(
            lot=lot,
            type=MouvementStock.Type.ENTREE,
            quantite=quantite,
            motif=f"Réception {reception} — commande {commande.numero}",
            utilisateur=utilisateur,
        )

    complete = all(l.quantite_a_recevoir == 0 for l in commande.lignes.all())
    commande.statut = (
        CommandeAchat.Statut.RECEPTIONNEE if complete else CommandeAchat.Statut.PARTIELLE
    )
    commande.save(update_fields=["statut"])
    audit.enregistrer(
        utilisateur, "Réception enregistrée", reception,
        f"{commande.numero} — {len(saisies)} ligne(s) — statut : {commande.get_statut_display()}",
    )
    return reception
