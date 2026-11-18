from .models import JournalAudit


def enregistrer(utilisateur, action, objet="", detail=""):
    """Ajoute une entrée au journal d'audit (auteur et date automatiques, RG09)."""
    if utilisateur is not None and not utilisateur.is_authenticated:
        utilisateur = None
    return JournalAudit.objects.create(
        utilisateur=utilisateur, action=action, objet=str(objet)[:150], detail=detail
    )
