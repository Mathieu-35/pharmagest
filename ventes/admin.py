from django.contrib import admin

from .models import LigneVente, Paiement, RetourVente, Vente


class LigneVenteInline(admin.TabularInline):
    model = LigneVente
    extra = 0


class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 0


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ("numero", "date", "client", "vendeur", "statut", "total")
    list_filter = ("statut", "vendeur")
    search_fields = ("client__nom",)
    readonly_fields = ("date", "jeton")
    inlines = [LigneVenteInline, PaiementInline]

    def has_delete_permission(self, request, obj=None):
        return False  # une vente validée ne se supprime pas (RG10) : on l'annule


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ("vente", "mode", "montant", "statut", "date")
    list_filter = ("mode", "statut")


@admin.register(RetourVente)
class RetourVenteAdmin(admin.ModelAdmin):
    list_display = ("ligne_vente", "quantite", "motif", "remis_en_stock", "enregistre_par", "date")
    list_filter = ("remis_en_stock",)
