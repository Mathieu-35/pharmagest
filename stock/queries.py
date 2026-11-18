from django.conf import settings
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


def jours_alerte_peremption():
    return settings.JOURS_ALERTE_PEREMPTION


def avec_stock(medicaments):
    """Ajoute à une liste de médicaments :
    - stock_disponible : lots vendables (ni bloqués, ni périmés) — RG08 ;
    - stock_non_vendable : lots bloqués ou périmés.
    """
    aujourdhui = timezone.localdate()
    vendable = Q(lots__bloque=False, lots__date_peremption__gte=aujourdhui)
    return medicaments.annotate(
        stock_disponible=Coalesce(Sum("lots__quantite_restante", filter=vendable), 0),
        stock_non_vendable=Coalesce(Sum("lots__quantite_restante", filter=~vendable), 0),
    )


def en_rupture(medicaments_avec_stock):
    return medicaments_avec_stock.filter(stock_disponible=0)


def sous_le_seuil(medicaments_avec_stock):
    """Stock strictement inférieur au seuil d'alerte, mais pas en rupture."""
    return medicaments_avec_stock.filter(
        stock_disponible__gt=0, stock_disponible__lt=F("seuil_alerte")
    )
