from django.db import models


class Fournisseur(models.Model):
    nom = models.CharField("nom ou raison sociale", max_length=200)
    adresse = models.CharField("adresse", max_length=255, blank=True)
    telephone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    numero_fiscal = models.CharField(
        "numéro fiscal / identifiant professionnel", max_length=50, blank=True
    )
    contact_principal = models.CharField("contact principal", max_length=150, blank=True)
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "fournisseur"
        verbose_name_plural = "fournisseurs"
        ordering = ["nom"]

    def __str__(self):
        return self.nom
