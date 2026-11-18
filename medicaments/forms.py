from django import forms

from .models import Categorie, Medicament


class BootstrapFormMixin:
    """Applique les classes Bootstrap 5 aux champs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            widget = champ.widget
            if isinstance(widget, forms.CheckboxInput):
                classe = "form-check-input"
            elif isinstance(widget, forms.Select):
                classe = "form-select"
            else:
                classe = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {classe}".strip()


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
