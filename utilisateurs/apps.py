from django.apps import AppConfig
from django.db.models.signals import post_migrate


class UtilisateursConfig(AppConfig):
    name = "utilisateurs"
    verbose_name = "Utilisateurs"

    def ready(self):
        from . import signals  # noqa: F401  (journal des connexions)
        from .roles import creer_roles

        post_migrate.connect(creer_roles, sender=self)
