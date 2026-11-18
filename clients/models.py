from django.db import models


class Client(models.Model):
    """Données limitées au strict nécessaire. Une vente comptoir n'exige pas de client."""

    nom = models.CharField("nom", max_length=150)
    telephone = models.CharField("téléphone", max_length=30, blank=True)
    adresse = models.CharField("adresse", max_length=255, blank=True)
    actif = models.BooleanField("actif", default=True)
    date_creation = models.DateTimeField("date de création", auto_now_add=True)

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ["nom"]

    def __str__(self):
        return self.nom
