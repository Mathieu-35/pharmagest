import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from clients.models import Client
from medicaments.models import Medicament
from stock.queries import avec_stock
from utilisateurs.decorators import permission_requise

from . import services
from .models import LigneVente, Paiement, RetourVente, Vente
from .panier import Panier

PAR_PAGE = 15


def _entier(valeur):
    try:
        return int(str(valeur).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------ Caisse

def _lignes_du_panier(panier):
    """Prépare l'affichage du panier : prix actuel, lots qui seraient utilisés (FEFO), alertes."""
    lignes, total, valide = [], Decimal("0"), bool(panier.lignes)
    for index, ligne in enumerate(panier.lignes):
        medicament = Medicament.objects.filter(pk=ligne["medicament_id"]).first()
        if medicament is None:
            panier.retirer(index)
            return _lignes_du_panier(panier)
        erreur, repartition = None, []
        if not medicament.est_actif:
            erreur = "Médicament archivé."
        else:
            try:
                repartition = services.allouer(medicament, ligne["quantite"], ligne["lot_id"])
            except services.ErreurVente as e:
                erreur = str(e)
        sous_total = ligne["quantite"] * medicament.prix_vente
        total += sous_total
        valide = valide and erreur is None
        lignes.append({
            "index": index, "medicament": medicament, "quantite": ligne["quantite"],
            "lot_id": ligne["lot_id"], "repartition": repartition, "erreur": erreur,
            "prix": medicament.prix_vente, "sous_total": sous_total,
        })
    return lignes, total, valide


@permission_requise("ventes.add_vente")
def caisse(request):
    panier = Panier(request.session)
    lignes, total, valide = _lignes_du_panier(panier)

    q = request.GET.get("q", "").strip()
    resultats = []
    if q:
        resultats = list(
            avec_stock(Medicament.objects.filter(statut=Medicament.Statut.ACTIF))
            .filter(Q(nom_commercial__icontains=q) | Q(code_barres__icontains=q))
            .order_by("nom_commercial")[:10]
        )
        for m in resultats:
            m.lots_choix = list(services.lots_vendables(m))

    return render(request, "ventes/caisse.html", {
        "panier": panier, "lignes": lignes, "total": total, "valide": valide,
        "q": q, "resultats": resultats,
        "clients": Client.objects.filter(actif=True).order_by("nom"),
        "modes": Paiement.Mode.choices,
    })


@permission_requise("ventes.add_vente")
@require_POST
def rechercher(request):
    """Recherche ou lecture d'un code-barres : un code exact ajoute directement 1 unité."""
    q = request.POST.get("q", "").strip()
    if q:
        exact = Medicament.objects.filter(
            code_barres=q, statut=Medicament.Statut.ACTIF).first()
        if exact:
            return _ajouter_au_panier(request, exact, 1, None)
        return redirect(f"{reverse('ventes:caisse')}?{urlencode({'q': q})}")
    return redirect("ventes:caisse")


def _ajouter_au_panier(request, medicament, quantite, lot_id):
    panier = Panier(request.session)
    if quantite is None or quantite < 1:
        messages.error(request, "La quantité doit être d'au moins 1.")
        return redirect("ventes:caisse")
    if not medicament.est_actif:
        messages.error(request, f"{medicament} est archivé : il ne peut pas être vendu.")
        return redirect("ventes:caisse")
    if lot_id and not services.lots_vendables(medicament, lot_id).exists():
        messages.error(request, "Ce lot n'est pas vendable (périmé, bloqué ou épuisé).")
        return redirect("ventes:caisse")
    demande = panier.quantite_de(medicament.pk, lot_id) + quantite
    disponible = services.stock_vendable(medicament, lot_id)
    if demande > disponible:
        messages.error(
            request,
            f"Stock insuffisant pour {medicament} : {demande} demandé(s) au total, "
            f"{disponible} disponible(s) à la vente.",
        )
        return redirect("ventes:caisse")
    panier.ajouter(medicament.pk, quantite, lot_id)
    messages.success(request, f"{quantite} × {medicament} ajouté(s) au panier.")
    return redirect("ventes:caisse")


@permission_requise("ventes.add_vente")
@require_POST
def panier_ajouter(request):
    medicament = get_object_or_404(Medicament, pk=_entier(request.POST.get("medicament")) or 0)
    lot_id = _entier(request.POST.get("lot"))
    return _ajouter_au_panier(request, medicament, _entier(request.POST.get("quantite")), lot_id)


@permission_requise("ventes.add_vente")
@require_POST
def panier_modifier(request, index):
    panier = Panier(request.session)
    quantite = _entier(request.POST.get("quantite"))
    if not (0 <= index < len(panier.lignes)):
        return redirect("ventes:caisse")
    ligne = panier.lignes[index]
    if quantite is None or quantite < 1:
        messages.error(request, "La quantité doit être d'au moins 1.")
        return redirect("ventes:caisse")
    medicament = get_object_or_404(Medicament, pk=ligne["medicament_id"])
    disponible = services.stock_vendable(medicament, ligne["lot_id"])
    autres = panier.quantite_de(medicament.pk, ligne["lot_id"], hors_index=index)
    if quantite + autres > disponible:
        messages.error(request, f"Stock insuffisant pour {medicament} : {disponible} disponible(s) à la vente.")
        return redirect("ventes:caisse")
    panier.modifier(index, quantite)
    return redirect("ventes:caisse")


@permission_requise("ventes.add_vente")
@require_POST
def panier_retirer(request, index):
    Panier(request.session).retirer(index)
    return redirect("ventes:caisse")


@permission_requise("ventes.add_vente")
@require_POST
def panier_vider(request):
    Panier(request.session).vider()
    messages.info(request, "Le panier a été vidé.")
    return redirect("ventes:caisse")


@permission_requise("ventes.add_vente")
@require_POST
def valider(request):
    panier = Panier(request.session)
    jeton_poste = request.POST.get("jeton", "")

    if jeton_poste != panier.jeton:
        # Formulaire périmé : la vente a peut-être déjà été validée (double envoi)
        try:
            deja = Vente.objects.filter(jeton=uuid.UUID(jeton_poste)).first()
        except ValueError:
            deja = None
        if deja:
            messages.info(request, f"La vente {deja.numero} avait déjà été validée : rien n'a été enregistré une seconde fois.")
            return redirect("ventes:detail", pk=deja.pk)
        messages.error(request, "Le panier a changé : vérifiez-le et recommencez.")
        return redirect("ventes:caisse")

    client = None
    client_id = _entier(request.POST.get("client"))
    if client_id:
        client = Client.objects.filter(pk=client_id, actif=True).first()
        if client is None:
            messages.error(request, "Client introuvable ou inactif.")
            return redirect("ventes:caisse")

    try:
        vente, creee = services.valider_vente(
            request.user, panier.lignes, request.POST.get("mode"), uuid.UUID(panier.jeton), client
        )
    except services.ErreurVente as erreur:
        messages.error(request, str(erreur))
        return redirect("ventes:caisse")

    panier.vider()
    if creee:
        messages.success(request, f"Vente {vente.numero} enregistrée : le stock a été mis à jour.")
    else:
        messages.info(request, f"La vente {vente.numero} avait déjà été validée : rien n'a été enregistré une seconde fois.")
    return redirect("ventes:detail", pk=vente.pk)


# -------------------------------------------------------------------- Historique

@permission_requise("ventes.view_vente")
def liste_ventes(request):
    ventes = Vente.objects.select_related("client", "vendeur").prefetch_related("lignes", "paiements")

    q = request.GET.get("q", "").strip()
    if q:
        numero = q.upper().removeprefix("V-").lstrip("0")
        filtre = Q(client__nom__icontains=q)
        if numero.isdigit():
            filtre |= Q(pk=int(numero))
        ventes = ventes.filter(filtre)

    statut = request.GET.get("statut", "")
    if statut in Vente.Statut.values:
        ventes = ventes.filter(statut=statut)
    else:
        statut = ""

    du, au = request.GET.get("du", ""), request.GET.get("au", "")
    if parse_date(du):
        ventes = ventes.filter(date__date__gte=parse_date(du))
    else:
        du = ""
    if parse_date(au):
        ventes = ventes.filter(date__date__lte=parse_date(au))
    else:
        au = ""

    page = Paginator(ventes, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "ventes/liste.html", {
        "page": page, "q": q, "statut": statut, "du": du, "au": au,
        "statuts": Vente.Statut.choices, "querystring": params.urlencode(),
    })


@permission_requise("ventes.view_vente")
def detail_vente(request, pk):
    vente = get_object_or_404(Vente.objects.select_related("client", "vendeur"), pk=pk)
    return render(request, "ventes/detail.html", {
        "vente": vente,
        "lignes": vente.lignes.select_related("medicament", "lot"),
        "paiements": vente.paiements.all(),
        "retours": RetourVente.objects.filter(ligne_vente__vente=vente)
        .select_related("ligne_vente__medicament", "enregistre_par"),
        "modes": Paiement.Mode.choices,
    })


# --------------------------------------------------------------------- Paiements

def _retour_detail(request, pk, action):
    try:
        action()
    except services.ErreurVente as erreur:
        messages.error(request, str(erreur))
    return redirect("ventes:detail", pk=pk)


@permission_requise("ventes.add_paiement")
@require_POST
def paiement_ajouter(request, pk):
    vente = get_object_or_404(Vente, pk=pk)
    try:
        montant = Decimal(request.POST.get("montant", "").replace(",", ".").strip())
    except InvalidOperation:
        montant = None

    def action():
        services.ajouter_paiement(
            request.user, vente.pk, request.POST.get("mode"), montant,
            request.POST.get("reference", ""))
        messages.success(request, "Paiement ajouté.")

    return _retour_detail(request, vente.pk, action)


@permission_requise("ventes.change_paiement")
@require_POST
def paiement_confirmer(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)

    def action():
        services.confirmer_paiement(request.user, paiement.pk, request.POST.get("reference", ""))
        messages.success(request, "Paiement confirmé.")

    return _retour_detail(request, paiement.vente_id, action)


@permission_requise("ventes.change_paiement")
@require_POST
def paiement_echoue(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)

    def action():
        services.declarer_paiement_echoue(request.user, paiement.pk)
        messages.warning(request, "Paiement déclaré échoué.")

    return _retour_detail(request, paiement.vente_id, action)


# --------------------------------------------------------------- Retours / annulation

@permission_requise("ventes.add_retourvente")
def retour(request, pk):
    vente = get_object_or_404(Vente.objects.select_related("client"), pk=pk)
    if vente.statut == Vente.Statut.ANNULEE:
        messages.error(request, "Cette vente est annulée : tout a déjà été retourné.")
        return redirect("ventes:detail", pk=vente.pk)

    lignes = [l for l in vente.lignes.select_related("medicament", "lot") if l.quantite_retournable > 0]
    if not lignes:
        messages.info(request, "Tout a déjà été retourné pour cette vente.")
        return redirect("ventes:detail", pk=vente.pk)

    motif, saisies = "", {}
    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        retours, erreur_saisie = [], False
        for ligne in lignes:
            brut = request.POST.get(f"quantite_{ligne.pk}", "").strip()
            remettre = request.POST.get(f"remettre_{ligne.pk}") == "on"
            saisies[ligne.pk] = {"quantite": brut, "remettre": remettre}
            if brut in ("", "0"):
                continue
            quantite = _entier(brut)
            if quantite is None or quantite < 1:
                messages.error(request, f"{ligne.medicament} : quantité invalide.")
                erreur_saisie = True
                continue
            retours.append({"ligne_id": ligne.pk, "quantite": quantite, "remettre_en_stock": remettre})
        if not erreur_saisie:
            try:
                crees = services.retourner(request.user, vente.pk, retours, motif)
            except services.ErreurVente as erreur:
                messages.error(request, str(erreur))
            else:
                montant = sum(r.montant_rembourse for r in crees)
                messages.success(request, f"Retour enregistré. Montant à rembourser : {montant}.")
                return redirect("ventes:detail", pk=vente.pk)

    return render(request, "ventes/retour.html", {
        "vente": vente, "motif": motif,
        "lignes": [
            {"ligne": l, "saisie": saisies.get(l.pk, {}),
             "eligible": not (l.lot.bloque or l.lot.est_perime)}
            for l in lignes
        ],
    })


@permission_requise("ventes.add_retourvente")
def annuler(request, pk):
    vente = get_object_or_404(Vente.objects.select_related("client"), pk=pk)
    if not vente.est_annulable:
        messages.error(request, "Cette vente est déjà annulée.")
        return redirect("ventes:detail", pk=vente.pk)
    if request.method == "POST":
        try:
            _, non_remises = services.annuler_vente(
                request.user, vente.pk, request.POST.get("motif", ""),
                request.POST.get("remettre") == "on")
        except services.ErreurVente as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"La vente {vente.numero} est annulée (opération compensatoire).")
            if non_remises:
                messages.warning(
                    request,
                    f"{non_remises} ligne(s) n'ont pas été remises en stock : lot périmé ou bloqué.")
            return redirect("ventes:detail", pk=vente.pk)
    return render(request, "ventes/annuler.html", {
        "vente": vente, "motif": request.POST.get("motif", ""),
    })
