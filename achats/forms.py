from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from config.formulaires import BootstrapFormMixin
from fournisseurs.models import Fournisseur
from medicaments.models import Medicament

from .models import CommandeAchat, LigneAchat


class CommandeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CommandeAchat
        fields = ["fournisseur"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Seuls les fournisseurs actifs (et le fournisseur déjà choisi) sont proposés
        filtre = Fournisseur.objects.filter(actif=True)
        if self.instance.pk:
            filtre = Fournisseur.objects.filter(actif=True) | Fournisseur.objects.filter(
                pk=self.instance.fournisseur_id
            )
        self.fields["fournisseur"].queryset = filtre.order_by("nom")


class LigneAchatForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LigneAchat
        fields = ["medicament", "quantite", "prix_achat"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medicament"].queryset = Medicament.objects.filter(
            statut=Medicament.Statut.ACTIF
        ).order_by("nom_commercial")


class BaseLigneAchatFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lignes = [
            f for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE")
        ]
        if not lignes:
            raise forms.ValidationError("Ajoutez au moins un médicament à la commande.")


def formset_lignes(extra):
    return inlineformset_factory(
        CommandeAchat, LigneAchat, form=LigneAchatForm, formset=BaseLigneAchatFormSet,
        extra=extra, can_delete=True,
    )


class ReceptionForm(BootstrapFormMixin, forms.Form):
    """Une ligne de saisie (quantité, lot, péremption) par ligne de commande restant à recevoir."""

    def __init__(self, *args, lignes, **kwargs):
        super().__init__(*args, **kwargs)
        self.lignes = list(lignes)
        for ligne in self.lignes:
            self.fields[f"quantite_{ligne.pk}"] = forms.IntegerField(
                label="Quantité reçue", min_value=0, required=False,
                initial=ligne.quantite_a_recevoir,
            )
            self.fields[f"lot_{ligne.pk}"] = forms.CharField(
                label="N° de lot", max_length=100, required=False
            )
            self.fields[f"peremption_{ligne.pk}"] = forms.DateField(
                label="Date de péremption", required=False,
                widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            )
        # BootstrapFormMixin ne connaît pas encore ces champs ajoutés après coup
        for nom, champ in self.fields.items():
            if "form-control" not in champ.widget.attrs.get("class", ""):
                champ.widget.attrs["class"] = "form-control"

    def champs_par_ligne(self):
        return [
            {
                "ligne": l,
                "quantite": self[f"quantite_{l.pk}"],
                "lot": self[f"lot_{l.pk}"],
                "peremption": self[f"peremption_{l.pk}"],
            }
            for l in self.lignes
        ]

    def clean(self):
        donnees = super().clean()
        aujourdhui = timezone.localdate()
        saisies = []
        for ligne in self.lignes:
            quantite = donnees.get(f"quantite_{ligne.pk}") or 0
            if quantite == 0:
                continue
            if quantite > ligne.quantite_a_recevoir:
                self.add_error(
                    f"quantite_{ligne.pk}",
                    f"Maximum {ligne.quantite_a_recevoir} (reste à recevoir).",
                )
            numero = (donnees.get(f"lot_{ligne.pk}") or "").strip()
            if not numero:
                self.add_error(f"lot_{ligne.pk}", "Indiquez le numéro de lot.")
            date = donnees.get(f"peremption_{ligne.pk}")
            if not date:
                self.add_error(f"peremption_{ligne.pk}", "Indiquez la date de péremption.")
            elif date < aujourdhui:
                self.add_error(f"peremption_{ligne.pk}", "Ce lot est déjà périmé.")
            saisies.append({
                "ligne_id": ligne.pk, "quantite": quantite,
                "numero_lot": numero, "date_peremption": date,
            })
        if not saisies and not self.errors:
            raise forms.ValidationError("Indiquez au moins une quantité reçue.")
        donnees["saisies"] = saisies
        return donnees
