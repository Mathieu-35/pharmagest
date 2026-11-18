import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Vente(models.Model):
    class Statut(models.TextChoices):
        VALIDEE = "validee", "Validée"
        ANNULEE = "annulee", "Annulée"

    client = models.ForeignKey(
        "clients.Client",
        verbose_name="client",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ventes",
        help_text="Vide pour une vente comptoir.",
    )
    vendeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="vendeur",
        on_delete=models.PROTECT,
        related_name="ventes",
    )
    # Jeton unique généré à l'ouverture du panier : empêche la double validation
    jeton = models.UUIDField("jeton anti-doublon", default=uuid.uuid4, unique=True, editable=False)
    statut = models.CharField(
        "statut", max_length=10, choices=Statut.choices, default=Statut.VALIDEE
    )
    date = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "vente"
        verbose_name_plural = "ventes"
        ordering = ["-date"]

    def __str__(self):
        return self.numero

    @property
    def numero(self):
        return f"V-{self.pk:06d}" if self.pk else "V-nouvelle"

    @property
    def total(self):
        return sum((l.sous_total for l in self.lignes.all()), Decimal("0"))

    @property
    def total_paye(self):
        """Seuls les paiements confirmés comptent."""
        return sum(
            (p.montant for p in self.paiements.all() if p.statut == Paiement.Statut.CONFIRME),
            Decimal("0"),
        )


class LigneVente(models.Model):
    vente = models.ForeignKey(
        Vente, verbose_name="vente", on_delete=models.CASCADE, related_name="lignes"
    )
    medicament = models.ForeignKey(
        "medicaments.Medicament",
        verbose_name="médicament",
        on_delete=models.PROTECT,
        related_name="lignes_vente",
    )
    lot = models.ForeignKey(
        "stock.LotStock",
        verbose_name="lot délivré",
        on_delete=models.PROTECT,
        related_name="lignes_vente",
    )
    quantite = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    # RG12 : prix figé au moment de la transaction
    prix_applique = models.DecimalField(
        "prix appliqué",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = "ligne de vente"
        verbose_name_plural = "lignes de vente"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantite__gte=1), name="ligne_vente_quantite_positive"
            ),
            models.CheckConstraint(
                condition=Q(prix_applique__gte=0), name="ligne_vente_prix_positif"
            ),
        ]

    def __str__(self):
        return f"{self.quantite} × {self.medicament}"

    def clean(self):
        if self.lot_id and self.medicament_id and self.lot.medicament_id != self.medicament_id:
            raise ValidationError("Le lot ne correspond pas au médicament.")

    @property
    def sous_total(self):
        return self.quantite * self.prix_applique


class Paiement(models.Model):
    class Mode(models.TextChoices):
        ESPECES = "especes", "Espèces"
        MOBILE_MONEY = "mobile_money", "Mobile money"
        AUTRE = "autre", "Autre moyen autorisé"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        CONFIRME = "confirme", "Confirmé"
        ECHOUE = "echoue", "Échoué"

    vente = models.ForeignKey(
        Vente, verbose_name="vente", on_delete=models.PROTECT, related_name="paiements"
    )
    mode = models.CharField("mode de paiement", max_length=15, choices=Mode.choices)
    montant = models.DecimalField(
        "montant", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    statut = models.CharField(
        "statut", max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE
    )
    reference_transaction = models.CharField(
        "référence de transaction", max_length=100, blank=True
    )
    date = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "paiement"
        verbose_name_plural = "paiements"
        ordering = ["-date"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="paiement_montant_positif"),
        ]

    def __str__(self):
        return f"{self.get_mode_display()} {self.montant} ({self.get_statut_display()})"


class RetourVente(models.Model):
    """Un retour est une opération compensatoire : la vente d'origine est conservée."""

    ligne_vente = models.ForeignKey(
        LigneVente,
        verbose_name="ligne de vente d'origine",
        on_delete=models.PROTECT,
        related_name="retours",
    )
    quantite = models.PositiveIntegerField("quantité retournée", validators=[MinValueValidator(1)])
    motif = models.CharField("motif du retour", max_length=255)
    remis_en_stock = models.BooleanField("remis en stock", default=False)
    enregistre_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="enregistré par",
        on_delete=models.PROTECT,
        related_name="retours_vente",
    )
    date = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "retour de vente"
        verbose_name_plural = "retours de vente"
        ordering = ["-date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantite__gte=1), name="retour_quantite_positive"
            ),
        ]

    def __str__(self):
        return f"Retour de {self.quantite} × {self.ligne_vente.medicament}"

    def clean(self):
        if self.ligne_vente_id and self.quantite:
            deja = sum(
                r.quantite
                for r in self.ligne_vente.retours.exclude(pk=self.pk)
            )
            if deja + self.quantite > self.ligne_vente.quantite:
                raise ValidationError(
                    "La quantité retournée dépasse la quantité vendue."
                )
