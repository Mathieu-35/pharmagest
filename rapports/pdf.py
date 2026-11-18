"""Génération des documents et rapports PDF avec ReportLab.

Chaque document comporte : informations de la pharmacie, numéro, date, lignes, quantités,
prix et total (cahier des charges, 4.11). Aucune donnée n'est saisie ici : tout vient de la base.
"""

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab import rl_config
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import statistiques

VERT = colors.HexColor("#198754")
GRIS = colors.HexColor("#6c757d")
CLAIR = colors.HexColor("#f1f3f5")

_styles = getSampleStyleSheet()
NORMAL = ParagraphStyle("normal", parent=_styles["Normal"], fontName="Helvetica", fontSize=9, leading=12)
PETIT = ParagraphStyle("petit", parent=NORMAL, fontSize=8, leading=10, textColor=GRIS)
TITRE = ParagraphStyle("titre", parent=NORMAL, fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=2)
SOUS_TITRE = ParagraphStyle("sous_titre", parent=NORMAL, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=8, spaceAfter=3)
NOM_PHARMACIE = ParagraphStyle("nom", parent=NORMAL, fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=VERT)
DROITE = ParagraphStyle("droite", parent=NORMAL, alignment=2)
ALERTE = ParagraphStyle("alerte", parent=NORMAL, fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#dc3545"))


# ----------------------------------------------------------------------- Outils

def montant(valeur):
    """12345.5 → « 12 345,50 Ar »."""
    valeur = Decimal(valeur or 0)
    texte = f"{valeur:,.2f}".replace(",", " ").replace(".", ",")
    return f"{texte} {settings.DEVISE}"


def date_heure(valeur):
    return timezone.localtime(valeur).strftime("%d/%m/%Y %H:%M")


def p(texte, style=NORMAL):
    """Paragraphe avec échappement du texte (un « & » ou « < » ne casse pas le PDF)."""
    return Paragraph(escape(str(texte)), style)


def _entete(titre, numero=None, date=None):
    infos = settings.PHARMACIE
    lignes = [p(infos["nom"], NOM_PHARMACIE)]
    for cle, etiquette in (("adresse", ""), ("telephone", "Tél. : "), ("email", "E-mail : "),
                           ("numero_fiscal", "N° fiscal : ")):
        if infos.get(cle):
            lignes.append(p(f"{etiquette}{infos[cle]}", PETIT))
    gauche = lignes
    droite = [p(titre, TITRE)]
    if numero:
        droite.append(p(f"N° {numero}", NORMAL))
    if date:
        droite.append(p(f"Date : {date}", NORMAL))
    tableau = Table([[gauche, droite]], colWidths=["52%", "48%"])
    tableau.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, VERT),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [tableau, Spacer(1, 6)]


def _tableau(entetes, lignes, largeurs=None, alignements_droite=(), total=None):
    """Tableau de données ; `total` = (libellé, valeur) ajouté en dernière ligne."""
    donnees = [[p(e, ParagraphStyle("th", parent=NORMAL, fontName="Helvetica-Bold", textColor=colors.white))
                for e in entetes]]
    for ligne in lignes:
        donnees.append([
            p(c, DROITE if i in alignements_droite else NORMAL) for i, c in enumerate(ligne)
        ])
    if total:
        vide = [""] * (len(entetes) - 2)
        donnees.append(vide + [p(total[0], ParagraphStyle("tl", parent=DROITE, fontName="Helvetica-Bold")),
                               p(total[1], ParagraphStyle("tv", parent=DROITE, fontName="Helvetica-Bold"))])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), VERT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1 if not total else -2), 0.25, colors.HexColor("#ced4da")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1 if not total else -2), [colors.white, CLAIR]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if total:
        style += [("LINEABOVE", (0, -1), (-1, -1), 1, VERT), ("SPAN", (0, -1), (-3, -1))]
    tableau = Table(donnees, colWidths=largeurs, repeatRows=1)
    tableau.setStyle(TableStyle(style))
    return tableau


def _pied(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRIS)
    mentions = settings.PHARMACIE.get("mentions_legales", "")
    if mentions:
        canvas.drawString(doc.leftMargin, 12 * mm, mentions[:150])
    canvas.drawString(doc.leftMargin, 8 * mm, f"{settings.PHARMACIE['nom']} — document généré le {date_heure(timezone.now())}")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _construire(titre, elements, format_page=A4):
    tampon = BytesIO()
    document = SimpleDocTemplate(
        tampon, pagesize=format_page, title=titre, author=settings.PHARMACIE["nom"],
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=20 * mm,
        pageCompression=rl_config.pageCompression,
    )
    document.build(elements, onFirstPage=_pied, onLaterPages=_pied)
    return tampon.getvalue()


def _bloc(titre, lignes):
    """Petit bloc d'informations « étiquette : valeur »."""
    elements = [p(titre, SOUS_TITRE)]
    for etiquette, valeur in lignes:
        elements.append(Paragraph(f"<b>{escape(etiquette)}</b> {escape(str(valeur))}", NORMAL))
    return elements


# ------------------------------------------------------------------ Ventes

def _lignes_vente(vente):
    return [
        [l.medicament, l.lot.numero_lot, l.quantite, montant(l.prix_applique), montant(l.sous_total)]
        for l in vente.lignes.select_related("medicament", "lot")
    ]


def _paiements_vente(vente):
    return [
        [p_.get_mode_display(), p_.get_statut_display(), p_.reference_transaction or "—", montant(p_.montant)]
        for p_ in vente.paiements.all()
    ]


def recu_vente(vente):
    elements = _entete("Reçu de vente", vente.numero, date_heure(vente.date))
    if vente.statut == vente.Statut.ANNULEE:
        elements.append(p("VENTE ANNULÉE", ALERTE))
    elements += _bloc("", [
        ("Vendeur :", vente.vendeur.username),
        ("Client :", vente.client.nom if vente.client else "Vente comptoir"),
    ])
    elements.append(Spacer(1, 4))
    elements.append(_tableau(
        ["Médicament", "Lot", "Qté", "Prix unit.", "Total"], _lignes_vente(vente),
        largeurs=[None, 22 * mm, 12 * mm, 22 * mm, 24 * mm], alignements_droite=(2, 3, 4),
        total=("Total", montant(vente.total)),
    ))
    paiements = _paiements_vente(vente)
    if paiements:
        elements.append(p("Paiements", SOUS_TITRE))
        elements.append(_tableau(["Mode", "Statut", "Référence", "Montant"], paiements,
                                 alignements_droite=(3,)))
    elements.append(Spacer(1, 4))
    elements.append(p(f"Paiement : {vente.libelle_paiement}", NORMAL))
    if vente.total_rembourse:
        elements.append(p(f"Total remboursé (retours) : {montant(vente.total_rembourse)}", NORMAL))
    elements.append(Spacer(1, 8))
    elements.append(p("Merci de votre confiance.", PETIT))
    return _construire(f"Reçu {vente.numero}", elements, A5)


def facture_vente(vente):
    numero = f"F-{vente.pk:06d}"
    elements = _entete("Facture", numero, date_heure(vente.date))
    if vente.statut == vente.Statut.ANNULEE:
        elements.append(p("VENTE ANNULÉE", ALERTE))
    client = vente.client
    elements += _bloc("Facturé à", [
        ("Nom :", client.nom if client else "Client comptoir"),
        *([("Téléphone :", client.telephone)] if client and client.telephone else []),
        *([("Adresse :", client.adresse)] if client and client.adresse else []),
    ])
    elements += _bloc("Référence", [("Vente :", vente.numero), ("Établie par :", vente.vendeur.username)])
    elements.append(Spacer(1, 6))
    elements.append(_tableau(
        ["Désignation", "Lot", "Quantité", "Prix unitaire", "Montant"], _lignes_vente(vente),
        largeurs=[None, 28 * mm, 22 * mm, 30 * mm, 32 * mm], alignements_droite=(2, 3, 4),
        total=("Total à payer", montant(vente.total)),
    ))
    elements.append(Spacer(1, 6))
    elements.append(p(f"Montant réglé : {montant(vente.total_paye)} — {vente.libelle_paiement}", NORMAL))
    return _construire(f"Facture {numero}", elements)


# ------------------------------------------------------------------- Achats

def bon_commande(commande):
    f = commande.fournisseur
    elements = _entete("Bon de commande", commande.numero, date_heure(commande.date_commande))
    elements.append(p(f"Statut : {commande.get_statut_display()}", NORMAL))
    elements += _bloc("Fournisseur", [
        ("Nom :", f.nom),
        *([("Adresse :", f.adresse)] if f.adresse else []),
        *([("Téléphone :", f.telephone)] if f.telephone else []),
        *([("E-mail :", f.email)] if f.email else []),
        *([("N° fiscal :", f.numero_fiscal)] if f.numero_fiscal else []),
        *([("Contact :", f.contact_principal)] if f.contact_principal else []),
    ])
    elements.append(Spacer(1, 6))
    elements.append(_tableau(
        ["Médicament", "Quantité", "Prix unitaire", "Montant"],
        [[l.medicament, l.quantite, montant(l.prix_achat), montant(l.sous_total)]
         for l in commande.lignes.select_related("medicament")],
        largeurs=[None, 25 * mm, 35 * mm, 35 * mm], alignements_droite=(1, 2, 3),
        total=("Total", montant(commande.montant_total)),
    ))
    elements.append(Spacer(1, 6))
    elements.append(p(f"Commande établie par : {commande.cree_par.username}", PETIT))
    return _construire(f"Bon de commande {commande.numero}", elements)


def bon_reception(reception):
    commande = reception.commande
    elements = _entete("Bon de réception", str(reception), date_heure(reception.date_reception))
    elements += _bloc("Référence", [
        ("Commande :", commande.numero),
        ("Fournisseur :", commande.fournisseur.nom),
        ("Reçu par :", reception.recue_par.username),
    ])
    elements.append(Spacer(1, 6))
    lignes = [
        [lr.ligne_achat.medicament, lr.lot.numero_lot, lr.lot.date_peremption.strftime("%d/%m/%Y"),
         lr.quantite, montant(lr.ligne_achat.prix_achat), montant(lr.quantite * lr.ligne_achat.prix_achat)]
        for lr in reception.lignes.select_related("ligne_achat__medicament", "lot")
    ]
    elements.append(_tableau(
        ["Médicament", "Lot", "Péremption", "Qté reçue", "Prix unitaire", "Montant"], lignes,
        largeurs=[None, 24 * mm, 24 * mm, 20 * mm, 28 * mm, 28 * mm], alignements_droite=(3, 4, 5),
        total=("Total réceptionné", montant(reception.montant)),
    ))
    return _construire(f"Bon de réception {reception}", elements)


# ----------------------------------------------------------------- Rapports

def _periode(du, au):
    return f"Période : du {du:%d/%m/%Y} au {au:%d/%m/%Y}"


def rapport_stock():
    from medicaments.models import Medicament
    from stock.queries import avec_stock

    medicaments = avec_stock(
        Medicament.objects.filter(statut=Medicament.Statut.ACTIF).select_related("categorie")
    ).order_by("nom_commercial")
    lignes = []
    for m in medicaments:
        if m.stock_disponible == 0:
            etat = "Rupture"
        elif m.stock_disponible < m.seuil_alerte:
            etat = "Stock faible"
        else:
            etat = "Normal"
        lignes.append([f"{m.nom_commercial} {m.dosage}".strip(), m.categorie.nom, m.stock_disponible,
                       m.seuil_alerte, m.stock_non_vendable, etat])
    elements = _entete("Rapport de stock", date=date_heure(timezone.now()))
    elements.append(p("Le stock disponible ne compte que les lots non périmés et non bloqués.", PETIT))
    elements.append(Spacer(1, 6))
    elements.append(_tableau(
        ["Médicament", "Catégorie", "Disponible", "Seuil", "Bloqué / périmé", "État"], lignes,
        largeurs=[None, 32 * mm, 22 * mm, 16 * mm, 26 * mm, 24 * mm], alignements_droite=(2, 3, 4)))
    return _construire("Rapport de stock", elements)


def rapport_ventes(du, au):
    stats = statistiques.statistiques_ventes(du, au, financieres=True)
    from ventes.models import Vente
    ventes = Vente.objects.filter(
        date__date__gte=du, date__date__lte=au).select_related("client", "vendeur").order_by("date")
    elements = _entete("Rapport des ventes", date=date_heure(timezone.now()))
    elements.append(p(_periode(du, au), NORMAL))
    elements.append(Spacer(1, 6))
    elements.append(_tableau(
        ["N°", "Date", "Client", "Vendeur", "Statut", "Total", "Paiement"],
        [[v.numero, date_heure(v.date), v.client.nom if v.client else "Comptoir", v.vendeur.username,
          v.get_statut_display(), montant(v.total), v.libelle_paiement] for v in ventes],
        alignements_droite=(5,)))
    elements.append(p("Synthèse de la période", SOUS_TITRE))
    elements.append(_tableau(["Indicateur", "Valeur"], [
        ["Nombre de ventes validées", stats["nombre_ventes"]],
        ["Chiffre d'affaires (ventes validées, net des retours)", montant(stats["ca"])],
        ["Encaissements (paiements confirmés)", montant(stats["encaissements"])],
        ["Paiements en attente de confirmation", montant(stats["en_attente"])],
        ["Remboursements de retours", montant(stats["remboursements"])],
        ["Coût d'achat des produits vendus", montant(stats["cout_achat"])],
        ["Marge commerciale brute", montant(stats["marge_brute"])],
    ], largeurs=[None, 45 * mm], alignements_droite=(1,)))
    elements.append(Spacer(1, 4))
    elements.append(p("La marge commerciale brute n'est pas un bénéfice net : les autres charges "
                      "(salaires, loyer, taxes...) ne sont pas prises en compte. Le chiffre d'affaires "
                      "n'est pas non plus égal aux encaissements.", PETIT))
    return _construire("Rapport des ventes", elements)


def rapport_achats(du, au):
    stats = statistiques.statistiques_achats(du, au)
    elements = _entete("Rapport des achats", date=date_heure(timezone.now()))
    elements.append(p(_periode(du, au), NORMAL))
    elements.append(p("Commandes passées (hors brouillons et commandes annulées)", SOUS_TITRE))
    elements.append(_tableau(
        ["N°", "Date", "Fournisseur", "Statut", "Montant"],
        [[c.numero, timezone.localtime(c.date_commande).strftime("%d/%m/%Y"), c.fournisseur.nom,
          c.get_statut_display(), montant(c.montant_total)] for c in stats["commandes"]],
        alignements_droite=(4,), total=("Total commandé", montant(stats["montant_commande"]))))
    elements.append(p("Réceptions de la période", SOUS_TITRE))
    elements.append(_tableau(
        ["Réception", "Date", "Commande", "Fournisseur", "Montant"],
        [[str(r), date_heure(r.date_reception), r.commande.numero, r.commande.fournisseur.nom,
          montant(r.montant)] for r in stats["receptions"]],
        alignements_droite=(4,), total=("Total réceptionné", montant(stats["montant_receptionne"]))))
    return _construire("Rapport des achats", elements)


def rapport_peremptions():
    jours = statistiques.jours_alerte()
    elements = _entete("Produits proches de la péremption", date=date_heure(timezone.now()))
    elements.append(p(f"Lots périmés encore en stock, et lots expirant dans les {jours} prochains jours.", NORMAL))

    def lignes(lots):
        return [[l.medicament, l.numero_lot, l.date_peremption.strftime("%d/%m/%Y"),
                 l.quantite_restante, "Oui" if l.bloque else "Non"] for l in lots]

    entetes = ["Médicament", "Lot", "Péremption", "Quantité", "Bloqué"]
    largeurs = [None, 35 * mm, 28 * mm, 22 * mm, 20 * mm]
    elements.append(p("Lots périmés (à retirer de la vente)", SOUS_TITRE))
    elements.append(_tableau(entetes, lignes(statistiques.lots_perimes_en_stock()),
                             largeurs=largeurs, alignements_droite=(3,)))
    elements.append(p(f"Péremption dans les {jours} jours", SOUS_TITRE))
    elements.append(_tableau(entetes, lignes(statistiques.lots_proches_de_la_peremption()),
                             largeurs=largeurs, alignements_droite=(3,)))
    return _construire("Produits proches de la péremption", elements)
