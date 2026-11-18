from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm,
)
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password

from config.formulaires import BootstrapFormMixin

from .roles import ADMINISTRATEUR

User = get_user_model()


class UtilisateurForm(BootstrapFormMixin, forms.ModelForm):
    """Création et modification d'un compte, avec ses rôles."""

    password1 = forms.CharField(
        label="Mot de passe", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmation du mot de passe", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    groups = forms.ModelMultipleChoiceField(
        label="Rôles", queryset=Group.objects.order_by("name"),
        required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Un utilisateur peut cumuler plusieurs rôles.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "groups"]
        labels = {"is_active": "Compte actif"}

    def __init__(self, *args, utilisateur_courant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur_courant = utilisateur_courant
        self.creation = self.instance.pk is None
        if self.creation:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
        else:
            self.fields["password1"].label = "Nouveau mot de passe"
            self.fields["password1"].help_text = "Laisser vide pour ne pas le changer."

    def clean(self):
        donnees = super().clean()
        mdp1, mdp2 = donnees.get("password1"), donnees.get("password2")
        if mdp1 or mdp2:
            if mdp1 != mdp2:
                self.add_error("password2", "Les deux mots de passe ne correspondent pas.")
            elif mdp1:
                try:
                    validate_password(mdp1, user=self.instance)
                except forms.ValidationError as erreur:
                    self.add_error("password1", erreur)

        # Un administrateur ne peut pas se couper lui-même l'accès
        if self.utilisateur_courant and self.instance.pk == self.utilisateur_courant.pk:
            if not donnees.get("is_active", True):
                self.add_error("is_active", "Vous ne pouvez pas désactiver votre propre compte.")
            if not self.instance.is_superuser:
                roles = donnees.get("groups")
                if roles is not None and not roles.filter(name=ADMINISTRATEUR).exists():
                    self.add_error("groups", "Vous ne pouvez pas retirer votre propre rôle d'administrateur.")
        return donnees

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            utilisateur.set_password(self.cleaned_data["password1"])
        roles = self.cleaned_data.get("groups")
        if not utilisateur.is_superuser:
            # L'accès à l'administration Django est réservé au rôle Administrateur
            utilisateur.is_staff = bool(roles and roles.filter(name=ADMINISTRATEUR).exists())
        utilisateur.save()
        self.save_m2m()
        return utilisateur


# Formulaires d'authentification de Django, habillés en Bootstrap
class ConnexionForm(BootstrapFormMixin, AuthenticationForm):
    pass


class ChangerMotDePasseForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class DemandeReinitialisationForm(BootstrapFormMixin, PasswordResetForm):
    pass


class NouveauMotDePasseForm(BootstrapFormMixin, SetPasswordForm):
    pass
