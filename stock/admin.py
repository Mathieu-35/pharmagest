from django.contrib import admin

from .models import LotStock, MouvementStock


@admin.register(LotStock)
class LotStockAdmin(admin.ModelAdmin):
    list_display = (
        "medicament", "numero_lot", "date_peremption",
        "quantite_recue", "quantite_restante", "bloque",
    )
    list_filter = ("bloque", "date_peremption")
    search_fields = ("medicament__nom_commercial", "numero_lot")


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ("date", "lot", "type", "quantite", "utilisateur", "motif")
    list_filter = ("type",)
    search_fields = ("lot__numero_lot", "lot__medicament__nom_commercial", "motif")
    readonly_fields = ("date",)
