from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import path, reverse_lazy

from . import views
from .forms import (
    ChangerMotDePasseForm, ConnexionForm, DemandeReinitialisationForm, NouveauMotDePasseForm,
)

app_name = "utilisateurs"

urlpatterns = [
    # Connexion / déconnexion
    path("connexion/", auth_views.LoginView.as_view(
        template_name="utilisateurs/connexion.html", redirect_authenticated_user=True,
        authentication_form=ConnexionForm),
        name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),

    # Mot de passe
    path("mot-de-passe/changer/", login_required(views.ChangerMotDePasseView.as_view()),
         name="mot_de_passe_changer"),
    path("mot-de-passe/oublie/", auth_views.PasswordResetView.as_view(
        template_name="utilisateurs/reinitialisation_demande.html",
        form_class=DemandeReinitialisationForm,
        email_template_name="utilisateurs/reinitialisation_email.txt",
        subject_template_name="utilisateurs/reinitialisation_sujet.txt",
        success_url=reverse_lazy("utilisateurs:reinitialisation_envoyee")),
        name="reinitialisation"),
    path("mot-de-passe/oublie/envoye/", auth_views.PasswordResetDoneView.as_view(
        template_name="utilisateurs/reinitialisation_envoyee.html"),
        name="reinitialisation_envoyee"),
    path("mot-de-passe/reinitialiser/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="utilisateurs/reinitialisation_confirmer.html",
        form_class=NouveauMotDePasseForm,
        success_url=reverse_lazy("utilisateurs:reinitialisation_terminee")),
        name="reinitialisation_confirmer"),
    path("mot-de-passe/reinitialiser/termine/", auth_views.PasswordResetCompleteView.as_view(
        template_name="utilisateurs/reinitialisation_terminee.html"),
        name="reinitialisation_terminee"),

    # Gestion des comptes (permissions Django : auth.*_user)
    path("", views.liste_utilisateurs, name="liste"),
    path("nouveau/", views.creer_utilisateur, name="creer"),
    path("<int:pk>/modifier/", views.modifier_utilisateur, name="modifier"),
    path("<int:pk>/activation/", views.basculer_activation, name="activation"),

    # Historique des opérations
    path("journal/", views.journal_audit, name="journal"),
]
