from django.contrib import admin

from .models import Categorie, Medicament


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "description")
    search_fields = ("nom",)


@admin.register(Medicament)
class MedicamentAdmin(admin.ModelAdmin):
    list_display = (
        "nom_commercial", "dosage", "forme", "categorie",
        "prix_achat", "prix_vente", "seuil_alerte", "statut",
    )
    list_filter = ("categorie", "forme", "statut")
    search_fields = ("nom_commercial", "denomination_generique", "code_barres")
    readonly_fields = ("date_creation",)
