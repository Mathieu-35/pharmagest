from django.contrib import admin

from .models import CommandeAchat, LigneAchat, LigneReception, ReceptionAchat


class LigneAchatInline(admin.TabularInline):
    model = LigneAchat
    extra = 1


@admin.register(CommandeAchat)
class CommandeAchatAdmin(admin.ModelAdmin):
    list_display = ("numero", "fournisseur", "statut", "montant_total", "cree_par", "date_commande")
    list_filter = ("statut", "fournisseur")
    search_fields = ("fournisseur__nom",)
    readonly_fields = ("date_commande",)
    inlines = [LigneAchatInline]


class LigneReceptionInline(admin.TabularInline):
    model = LigneReception
    extra = 0


@admin.register(ReceptionAchat)
class ReceptionAchatAdmin(admin.ModelAdmin):
    list_display = ("__str__", "commande", "recue_par", "date_reception")
    readonly_fields = ("date_reception",)
    inlines = [LigneReceptionInline]
