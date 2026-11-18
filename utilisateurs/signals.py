from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .audit import enregistrer


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    enregistrer(user, "Connexion", user.get_username())


@receiver(user_logged_out)
def journaliser_deconnexion(sender, request, user, **kwargs):
    if user is not None:
        enregistrer(user, "Déconnexion", user.get_username())
