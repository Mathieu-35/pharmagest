from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .audit import enregistrer


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    enregistrer(user, "Connexion", user.get_username())


@receiver(user_logged_out)
def journaliser_deconnexion(sender, request, user, **kwargs):
    if user is not None:
        enregistrer(user, "Déconnexion", user.get_username())


@receiver(user_login_failed)
def journaliser_echec_de_connexion(sender, credentials, request=None, **kwargs):
    """Trace les tentatives refusées (identifiant saisi uniquement, jamais le mot de passe)."""
    enregistrer(None, "Échec de connexion", str(credentials.get("username", "")))
