from django import forms

from config.formulaires import BootstrapFormMixin

from .models import Categorie, Medicament


class CategorieForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ["nom", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class MedicamentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Medicament
        fields = [
            "nom_commercial", "denomination_generique", "categorie", "forme",
            "dosage", "laboratoire", "code_barres", "photo",
            "prix_achat", "prix_vente", "seuil_alerte", "statut",
        ]
        widgets = {"photo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})}
