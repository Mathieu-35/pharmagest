from django import forms

from config.formulaires import BootstrapFormMixin

from .models import Fournisseur


class FournisseurForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Fournisseur
        fields = [
            "nom", "adresse", "telephone", "email",
            "numero_fiscal", "contact_principal", "actif",
        ]
