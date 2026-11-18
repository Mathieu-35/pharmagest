from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class LotStock(models.Model):
    medicament = models.ForeignKey(
        "medicaments.Medicament",
        verbose_name="médicament",
        on_delete=models.PROTECT,
        related_name="lots",
    )
    numero_lot = models.CharField("numéro de lot", max_length=100)
    date_peremption = models.DateField("date de péremption")
    quantite_recue = models.PositiveIntegerField(
        "quantité reçue", validators=[MinValueValidator(1)]
    )
    # PositiveIntegerField : la base refuse une quantité négative (RG07)
    quantite_restante = models.PositiveIntegerField("quantité restante")
    bloque = models.BooleanField("bloqué", default=False)
    date_creation = models.DateTimeField("date de création", auto_now_add=True)

    class Meta:
        verbose_name = "lot"
        verbose_name_plural = "lots"
        # Ordre FEFO : la péremption la plus proche en premier
        ordering = ["date_peremption", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["medicament", "numero_lot"], name="lot_unique_par_medicament"
            ),
            models.CheckConstraint(
                condition=Q(quantite_recue__gte=1), name="lot_quantite_recue_positive"
            ),
            models.CheckConstraint(
                condition=Q(quantite_restante__lte=F("quantite_recue")),
                name="lot_restante_inferieure_recue",
            ),
        ]

    def __str__(self):
        return f"{self.medicament} — lot {self.numero_lot}"

    def clean(self):
        if (
            self.quantite_restante is not None
            and self.quantite_recue is not None
            and self.quantite_restante > self.quantite_recue
        ):
            raise ValidationError(
                "La quantité restante ne peut pas dépasser la quantité reçue."
            )

    @property
    def est_perime(self):
        return self.date_peremption < timezone.localdate()

    @property
    def est_vendable(self):
        """RG08 : un lot périmé, bloqué ou vide n'est pas proposé à la vente."""
        return not self.bloque and not self.est_perime and self.quantite_restante > 0


class MouvementStock(models.Model):
    class Type(models.TextChoices):
        ENTREE = "entree", "Entrée (réception)"
        SORTIE = "sortie", "Sortie (vente)"
        RETOUR = "retour", "Retour en stock"
        CORRECTION = "correction", "Correction d'inventaire"

    lot = models.ForeignKey(
        LotStock,
        verbose_name="lot",
        on_delete=models.PROTECT,
        related_name="mouvements",
    )
    type = models.CharField("type", max_length=12, choices=Type.choices)
    quantite = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    motif = models.CharField("motif / référence", max_length=255, blank=True)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mouvements_stock",
    )
    date = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "mouvement de stock"
        verbose_name_plural = "mouvements de stock"
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantite__gte=1), name="mouvement_quantite_positive"
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} de {self.quantite} — {self.lot}"
