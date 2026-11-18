from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from medicaments.models import Medicament
from utilisateurs.decorators import permission_requise

from . import services
from .models import LotStock, MouvementStock
from .queries import avec_stock, en_rupture, jours_alerte_peremption, sous_le_seuil

PAR_PAGE = 15


def _paginer(request, queryset):
    page = Paginator(queryset, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


@permission_requise("stock.view_lotstock")
def stock_disponible(request):
    """Stock disponible par médicament, avec ruptures et stocks sous le seuil d'alerte."""
    medicaments = avec_stock(
        Medicament.objects.select_related("categorie").filter(statut=Medicament.Statut.ACTIF)
    )
    q = request.GET.get("q", "").strip()
    if q:
        medicaments = medicaments.filter(
            Q(nom_commercial__icontains=q) | Q(code_barres__icontains=q)
        )
    etat = request.GET.get("etat", "")
    if etat == "rupture":
        medicaments = en_rupture(medicaments)
    elif etat == "faible":
        medicaments = sous_le_seuil(medicaments)
    else:
        etat = ""
    page, querystring = _paginer(request, medicaments.order_by("nom_commercial", "id"))
    return render(request, "stock/disponible.html", {
        "page": page, "querystring": querystring, "q": q, "etat": etat,
    })


ETATS_LOTS = [
    ("actifs", "En stock"),
    ("proches", "Péremption proche"),
    ("perimes", "Périmés"),
    ("bloques", "Bloqués"),
    ("epuises", "Épuisés"),
    ("tous", "Tous"),
]


@permission_requise("stock.view_lotstock")
def liste_lots(request):
    aujourdhui = timezone.localdate()
    jours = jours_alerte_peremption()
    lots = LotStock.objects.select_related("medicament")

    etat = request.GET.get("etat", "actifs")
    if etat not in dict(ETATS_LOTS):
        etat = "actifs"
    en_stock = Q(quantite_restante__gt=0)
    if etat == "actifs":
        lots = lots.filter(en_stock)
    elif etat == "proches":
        lots = lots.filter(
            en_stock, date_peremption__gte=aujourdhui,
            date_peremption__lte=aujourdhui + timedelta(days=jours),
        )
    elif etat == "perimes":
        lots = lots.filter(en_stock, date_peremption__lt=aujourdhui)
    elif etat == "bloques":
        lots = lots.filter(en_stock, bloque=True)
    elif etat == "epuises":
        lots = lots.filter(quantite_restante=0)

    q = request.GET.get("q", "").strip()
    if q:
        lots = lots.filter(
            Q(medicament__nom_commercial__icontains=q) | Q(numero_lot__icontains=q)
        )

    page, querystring = _paginer(request, lots.order_by("date_peremption", "id"))
    return render(request, "stock/lots.html", {
        "page": page, "querystring": querystring, "q": q, "etat": etat,
        "etats": ETATS_LOTS, "aujourdhui": aujourdhui,
        "limite": aujourdhui + timedelta(days=jours), "jours": jours,
    })


@require_POST
@permission_requise("stock.change_lotstock")
def basculer_blocage(request, pk):
    lot = get_object_or_404(LotStock, pk=pk)
    lot = services.basculer_blocage(lot.pk, request.user)
    messages.success(
        request, f"Le lot {lot.numero_lot} est maintenant {'bloqué' if lot.bloque else 'débloqué'}."
    )
    return redirect("stock:lots")


@permission_requise("stock.view_mouvementstock")
def liste_mouvements(request):
    mouvements = MouvementStock.objects.select_related("lot__medicament", "utilisateur")
    type_ = request.GET.get("type", "")
    if type_ in MouvementStock.Type.values:
        mouvements = mouvements.filter(type=type_)
    else:
        type_ = ""
    q = request.GET.get("q", "").strip()
    if q:
        mouvements = mouvements.filter(
            Q(lot__medicament__nom_commercial__icontains=q)
            | Q(lot__numero_lot__icontains=q) | Q(motif__icontains=q)
        )
    page, querystring = _paginer(request, mouvements)
    return render(request, "stock/mouvements.html", {
        "page": page, "querystring": querystring, "q": q, "type": type_,
        "types": MouvementStock.Type.choices,
    })


@permission_requise("stock.add_mouvementstock", "stock.change_lotstock")
def inventaire(request):
    """Inventaire physique : on saisit les quantités comptées, les écarts deviennent
    des mouvements « correction »."""
    lots = list(
        LotStock.objects.select_related("medicament")
        .filter(quantite_restante__gt=0)
        .order_by("medicament__nom_commercial", "date_peremption")
    )
    motif = "Inventaire physique"
    saisies = {}
    erreurs = {}

    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        comptages = {}
        for lot in lots:
            brut = request.POST.get(f"compte_{lot.pk}", "").strip()
            saisies[lot.pk] = brut
            if brut == "":
                continue
            try:
                valeur = int(brut)
            except ValueError:
                erreurs[lot.pk] = "Nombre entier attendu."
                continue
            if valeur < 0:
                erreurs[lot.pk] = "Ne peut pas être négatif."
            elif valeur > lot.quantite_recue:
                erreurs[lot.pk] = f"Dépasse la quantité reçue ({lot.quantite_recue})."
            else:
                comptages[lot.pk] = valeur
        if not erreurs:
            try:
                corriges = services.corriger_inventaire(request.user, comptages, motif)
            except services.ErreurStock as erreur:
                messages.error(request, str(erreur))
            else:
                if corriges:
                    messages.success(request, f"Inventaire enregistré : {corriges} lot(s) corrigé(s).")
                else:
                    messages.info(request, "Inventaire enregistré : aucun écart constaté.")
                return redirect("stock:mouvements")

    lignes = [
        {
            "lot": lot,
            "valeur": saisies.get(lot.pk, lot.quantite_restante),
            "erreur": erreurs.get(lot.pk),
        }
        for lot in lots
    ]
    return render(request, "stock/inventaire.html", {"lignes": lignes, "motif": motif})
