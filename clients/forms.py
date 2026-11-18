from django import forms

from config.formulaires import BootstrapFormMixin

from .models import Client


class ClientForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = ["nom", "telephone", "adresse", "actif"]
