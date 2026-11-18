from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date

from achats.models import CommandeAchat, ReceptionAchat
from utilisateurs.decorators import permission_requise
from ventes.models import Vente

from . import pdf, statistiques

TABLEAU = "rapports.voir_tableau_de_bord"
FINANCES = "rapports.voir_statistiques_financieres"
RAPPORTS = "rapports.generer_rapports"


def _periode(request):
    """Période choisie (paramètres du / au), sinon du 1er du mois à aujourd'hui."""
    du_defaut, au_defaut = statistiques.periode_par_defaut()
    du = parse_date(request.GET.get("du", "")) or du_defaut
    au = parse_date(request.GET.get("au", "")) or au_defaut
    if du > au:
        du, au = au, du
    return du, au


# ------------------------------------------------------------- Tableau de bord

@login_required
def tableau_de_bord(request):
    """Page d'accueil : chaque bloc n'apparaît que si le rôle de l'utilisateur y donne accès."""
    utilisateur = request.user
    if not utilisateur.has_perm(TABLEAU):
        return render(request, "accueil.html")

    du, au = _periode(request)
    contexte = {"du": du, "au": au, "devise": settings.DEVISE}

    if utilisateur.has_perm("stock.view_lotstock"):
        contexte["stock"] = statistiques.statistiques_stock()

    if utilisateur.has_perm("ventes.view_vente"):
        contexte["ventes_du_jour"] = statistiques.ventes_du_jour()
        financieres = utilisateur.has_perm(FINANCES)
        contexte["ventes"] = statistiques.statistiques_ventes(du, au, financieres=financieres)
        contexte["financieres"] = financieres

    if utilisateur.has_perm(FINANCES) and utilisateur.has_perm("achats.view_commandeachat"):
        contexte["achats"] = statistiques.statistiques_achats(du, au)

    if contexte.get("ventes") and contexte["ventes"]["par_jour"]:
        maximum = max(j["ca"] for j in contexte["ventes"]["par_jour"]) or 1
        for jour in contexte["ventes"]["par_jour"]:
            jour["pourcentage"] = int(jour["ca"] * 100 / maximum)

    return render(request, "rapports/tableau_de_bord.html", contexte)


# --------------------------------------------------------------- Liste des rapports

@permission_requise(RAPPORTS)
def liste_rapports(request):
    du, au = _periode(request)
    utilisateur = request.user
    return render(request, "rapports/liste.html", {
        "du": du, "au": au,
        "peut_stock": utilisateur.has_perm("stock.view_lotstock"),
        "peut_ventes": utilisateur.has_perm("ventes.view_vente") and utilisateur.has_perm(FINANCES),
        "peut_achats": utilisateur.has_perm("achats.view_commandeachat"),
    })


# --------------------------------------------------------------------- PDF

def _reponse_pdf(contenu, nom_fichier):
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'inline; filename="{nom_fichier}"'
    return reponse


@permission_requise("ventes.view_vente")
def recu_vente(request, pk):
    vente = get_object_or_404(Vente.objects.select_related("client", "vendeur"), pk=pk)
    return _reponse_pdf(pdf.recu_vente(vente), f"recu-{vente.numero}.pdf")


@permission_requise("ventes.view_vente")
def facture_vente(request, pk):
    vente = get_object_or_404(Vente.objects.select_related("client", "vendeur"), pk=pk)
    return _reponse_pdf(pdf.facture_vente(vente), f"facture-F-{vente.pk:06d}.pdf")


@permission_requise("achats.view_commandeachat")
def bon_commande(request, pk):
    commande = get_object_or_404(
        CommandeAchat.objects.select_related("fournisseur", "cree_par"), pk=pk)
    return _reponse_pdf(pdf.bon_commande(commande), f"bon-commande-{commande.numero}.pdf")


@permission_requise("achats.view_receptionachat")
def bon_reception(request, pk):
    reception = get_object_or_404(
        ReceptionAchat.objects.select_related("commande__fournisseur", "recue_par"), pk=pk)
    return _reponse_pdf(pdf.bon_reception(reception), f"bon-reception-{reception}.pdf")


@permission_requise(RAPPORTS, "stock.view_lotstock")
def rapport_stock(request):
    return _reponse_pdf(pdf.rapport_stock(), "rapport-stock.pdf")


@permission_requise(RAPPORTS, "ventes.view_vente", FINANCES)
def rapport_ventes(request):
    du, au = _periode(request)
    return _reponse_pdf(pdf.rapport_ventes(du, au), f"rapport-ventes-{du}-{au}.pdf")


@permission_requise(RAPPORTS, "achats.view_commandeachat")
def rapport_achats(request):
    du, au = _periode(request)
    return _reponse_pdf(pdf.rapport_achats(du, au), f"rapport-achats-{du}-{au}.pdf")


@permission_requise(RAPPORTS, "stock.view_lotstock")
def rapport_peremptions(request):
    return _reponse_pdf(pdf.rapport_peremptions(), "produits-proches-peremption.pdf")
