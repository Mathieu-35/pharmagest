from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum


class CommandeAchat(models.Model):
    """Une commande ne modifie jamais le stock (RG04) : seule la réception le fait."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        COMMANDEE = "commandee", "Commandée"
        PARTIELLE = "partielle", "Partiellement réceptionnée"
        RECEPTIONNEE = "receptionnee", "Entièrement réceptionnée"
        ANNULEE = "annulee", "Annulée"

    fournisseur = models.ForeignKey(
        "fournisseurs.Fournisseur",
        verbose_name="fournisseur",
        on_delete=models.PROTECT,
        related_name="commandes",
    )
    statut = models.CharField(
        "statut", max_length=15, choices=Statut.choices, default=Statut.BROUILLON
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="créée par",
        on_delete=models.PROTECT,
        related_name="commandes_achat",
    )
    date_commande = models.DateTimeField("date de création", auto_now_add=True)

    class Meta:
        verbose_name = "commande d'achat"
        verbose_name_plural = "commandes d'achat"
        ordering = ["-date_commande"]

    def __str__(self):
        return self.numero

    @property
    def numero(self):
        return f"CA-{self.pk:06d}" if self.pk else "CA-nouvelle"

    @property
    def montant_total(self):
        """Calculé à partir des lignes (jamais saisi à la main)."""
        return sum((l.sous_total for l in self.lignes.all()), Decimal("0"))

    @property
    def montant_receptionne(self):
        """Valeur des marchandises effectivement reçues, au prix de la commande."""
        return sum((r.montant for r in self.receptions.all()), Decimal("0"))

    @property
    def est_modifiable(self):
        return self.statut == self.Statut.BROUILLON

    @property
    def est_receptionnable(self):
        return self.statut in (self.Statut.COMMANDEE, self.Statut.PARTIELLE)

    @property
    def est_annulable(self):
        """Une commande déjà (même partiellement) réceptionnée ne s'annule plus."""
        return self.statut in (self.Statut.BROUILLON, self.Statut.COMMANDEE)


class LigneAchat(models.Model):
    commande = models.ForeignKey(
        CommandeAchat,
        verbose_name="commande",
        on_delete=models.CASCADE,
        related_name="lignes",
    )
    medicament = models.ForeignKey(
        "medicaments.Medicament",
        verbose_name="médicament",
        on_delete=models.PROTECT,
        related_name="lignes_achat",
    )
    quantite = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    prix_achat = models.DecimalField(
        "prix d'achat unitaire",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = "ligne d'achat"
        verbose_name_plural = "lignes d'achat"
        constraints = [
            models.UniqueConstraint(
                fields=["commande", "medicament"], name="ligne_achat_unique_par_commande"
            ),
            models.CheckConstraint(
                condition=Q(quantite__gte=1), name="ligne_achat_quantite_positive"
            ),
            models.CheckConstraint(
                condition=Q(prix_achat__gte=0), name="ligne_achat_prix_positif"
            ),
        ]

    def __str__(self):
        return f"{self.quantite} × {self.medicament}"

    @property
    def sous_total(self):
        return self.quantite * self.prix_achat

    @property
    def quantite_recue(self):
        return self.lignes_reception.aggregate(total=Sum("quantite"))["total"] or 0

    @property
    def quantite_a_recevoir(self):
        return self.quantite - self.quantite_recue


class ReceptionAchat(models.Model):
    """Réception effective de marchandises (totale ou partielle)."""

    commande = models.ForeignKey(
        CommandeAchat,
        verbose_name="commande",
        on_delete=models.PROTECT,
        related_name="receptions",
    )
    # Jeton unique généré à l'ouverture du formulaire : une réception ne peut être
    # enregistrée qu'une fois, même si le formulaire est envoyé deux fois (RG05)
    jeton = models.UUIDField("jeton anti-doublon", unique=True, null=True, editable=False)
    recue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="reçue par",
        on_delete=models.PROTECT,
        related_name="receptions_achat",
    )
    date_reception = models.DateTimeField("date de réception", auto_now_add=True)

    class Meta:
        verbose_name = "réception d'achat"
        verbose_name_plural = "réceptions d'achat"
        ordering = ["-date_reception"]

    def __str__(self):
        return f"BR-{self.pk:06d}" if self.pk else "BR-nouveau"

    @property
    def montant(self):
        return sum((l.quantite * l.ligne_achat.prix_achat for l in self.lignes.all()), Decimal("0"))


class LigneReception(models.Model):
    reception = models.ForeignKey(
        ReceptionAchat,
        verbose_name="réception",
        on_delete=models.CASCADE,
        related_name="lignes",
    )
    ligne_achat = models.ForeignKey(
        LigneAchat,
        verbose_name="ligne de commande",
        on_delete=models.PROTECT,
        related_name="lignes_reception",
    )
    lot = models.ForeignKey(
        "stock.LotStock",
        verbose_name="lot créé",
        on_delete=models.PROTECT,
        related_name="lignes_reception",
    )
    quantite = models.PositiveIntegerField(
        "quantité reçue", validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = "ligne de réception"
        verbose_name_plural = "lignes de réception"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantite__gte=1), name="ligne_reception_quantite_positive"
            ),
        ]

    def __str__(self):
        return f"{self.quantite} reçu(s) — {self.lot}"
