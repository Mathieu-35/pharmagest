"""Aides communes aux tests des rapports."""

import re
import uuid
from datetime import timedelta
from decimal import Decimal

from reportlab import rl_config

from achats import services as services_achats
from achats.models import CommandeAchat, LigneAchat
from fournisseurs.models import Fournisseur
from medicaments.models import Medicament
from ventes.outils_tests import CaisseTestCase


def texte_pdf(contenu):
    """Texte lisible d'un PDF non compressé (accents décodés)."""
    morceaux = re.findall(rb"\((.*?)\) Tj", contenu)
    texte = []
    for morceau in morceaux:
        brut = re.sub(rb"\\(\d{3})", lambda m: bytes([int(m.group(1), 8)]), morceau)
        texte.append(brut.decode("cp1252", errors="replace"))
    return "\n".join(texte)


class RapportsTestCase(CaisseTestCase):
    """Reprend la caisse (un médicament à 500, coût 300, deux lots) et désactive la
    compression des PDF pour pouvoir lire leur texte."""

    def setUp(self):
        super().setUp()
        self._compression = rl_config.pageCompression
        rl_config.pageCompression = 0

    def tearDown(self):
        rl_config.pageCompression = self._compression
        super().tearDown()

    def receptionner(self, medicament, quantite, prix_achat, numero_lot="REC-1", jours=200):
        """Commande puis réception complète : crée un lot dont le coût réel est `prix_achat`."""
        fournisseur = Fournisseur.objects.get_or_create(nom="Grossiste Test")[0]
        commande = CommandeAchat.objects.create(
            fournisseur=fournisseur, cree_par=self.caissier, statut=CommandeAchat.Statut.COMMANDEE)
        ligne = LigneAchat.objects.create(
            commande=commande, medicament=medicament, quantite=quantite, prix_achat=Decimal(prix_achat))
        reception, _ = services_achats.receptionner(commande.pk, self.caissier, uuid.uuid4(), [{
            "ligne_id": ligne.pk, "quantite": quantite, "numero_lot": numero_lot,
            "date_peremption": self.aujourdhui + timedelta(days=jours)}])
        return commande, reception
