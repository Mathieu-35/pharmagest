from django.db import models


class Rapport(models.Model):
    """Modèle sans table : il ne sert qu'à porter les permissions du tableau de bord
    et des rapports, attribuées aux rôles comme les autres permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("voir_tableau_de_bord", "Peut voir le tableau de bord"),
            ("voir_statistiques_financieres", "Peut voir le chiffre d'affaires, les encaissements et les marges"),
            ("generer_rapports", "Peut générer les rapports PDF"),
        ]
