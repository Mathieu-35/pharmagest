from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Categorie(models.Model):
    nom = models.CharField("nom", max_length=100, unique=True)
    description = models.TextField("description", blank=True)

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Medicament(models.Model):
    class Forme(models.TextChoices):
        COMPRIME = "comprime", "Comprimé"
        GELULE = "gelule", "Gélule"
        SIROP = "sirop", "Sirop"
        INJECTABLE = "injectable", "Injectable"
        POMMADE = "pommade", "Pommade"
        SOLUTION = "solution", "Solution"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        ARCHIVE = "archive", "Archivé"

    nom_commercial = models.CharField("nom commercial", max_length=200)
    denomination_generique = models.CharField(
        "dénomination générique", max_length=200, blank=True
    )
    categorie = models.ForeignKey(
        Categorie,
        verbose_name="catégorie",
        on_delete=models.PROTECT,
        related_name="medicaments",
    )
    forme = models.CharField(
        "forme pharmaceutique", max_length=20, choices=Forme.choices, default=Forme.COMPRIME
    )
    dosage = models.CharField("dosage", max_length=50, blank=True, help_text="Ex. : 500 mg")
    laboratoire = models.CharField("laboratoire", max_length=150, blank=True)
    code_barres = models.CharField(
        "code-barres", max_length=50, unique=True, null=True, blank=True
    )
    photo = models.ImageField("photo", upload_to="medicaments/", blank=True)
    prix_achat = models.DecimalField(
        "prix d'achat", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    prix_vente = models.DecimalField(
        "prix de vente", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    seuil_alerte = models.PositiveIntegerField("seuil d'alerte", default=10)
    statut = models.CharField(
        "statut", max_length=10, choices=Statut.choices, default=Statut.ACTIF
    )
    date_creation = models.DateTimeField("date de création", auto_now_add=True)

    class Meta:
        verbose_name = "médicament"
        verbose_name_plural = "médicaments"
        ordering = ["nom_commercial"]
        constraints = [
            models.CheckConstraint(
                condition=Q(prix_achat__gte=0), name="medicament_prix_achat_positif"
            ),
            models.CheckConstraint(
                condition=Q(prix_vente__gte=0), name="medicament_prix_vente_positif"
            ),
        ]

    def __str__(self):
        return f"{self.nom_commercial} {self.dosage}".strip()

    def save(self, *args, **kwargs):
        # RG02 : un code-barres vide est stocké NULL pour ne pas violer l'unicité
        if not self.code_barres:
            self.code_barres = None
        super().save(*args, **kwargs)

    @property
    def est_actif(self):
        return self.statut == self.Statut.ACTIF
