from django.conf import settings
from django.db import models


class JournalAudit(models.Model):
    """Trace des opérations sensibles (RG09). Les comptes utilisateurs, rôles et
    permissions sont gérés par le système d'authentification de Django."""

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_audit",
    )
    action = models.CharField("action", max_length=100)
    objet = models.CharField("objet concerné", max_length=150, blank=True)
    detail = models.TextField("détail", blank=True)
    date = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "entrée du journal d'audit"
        verbose_name_plural = "journal d'audit"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date:%d/%m/%Y %H:%M} — {self.action}"
