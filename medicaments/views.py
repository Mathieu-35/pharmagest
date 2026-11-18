from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CategorieForm, MedicamentForm
from .models import Categorie, Medicament

PAR_PAGE = 10

TRIS_MEDICAMENTS = {
    "nom": "nom_commercial",
    "-nom": "-nom_commercial",
    "categorie": "categorie__nom",
    "prix": "prix_vente",
    "-prix": "-prix_vente",
    "stock": "stock_disponible",
    "-stock": "-stock_disponible",
}
LIBELLES_TRI = [
    ("nom", "Nom (A → Z)"),
    ("-nom", "Nom (Z → A)"),
    ("categorie", "Catégorie"),
    ("prix", "Prix de vente croissant"),
    ("-prix", "Prix de vente décroissant"),
    ("stock", "Stock croissant"),
    ("-stock", "Stock décroissant"),
]


def _paginer(request, queryset):
    page = Paginator(queryset, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


# ---------------------------------------------------------------- Médicaments

def liste_medicaments(request):
    aujourdhui = timezone.localdate()
    medicaments = Medicament.objects.select_related("categorie").annotate(
        # Stock disponible : lots non bloqués et non périmés (RG08)
        stock_disponible=Coalesce(
            Sum(
                "lots__quantite_restante",
                filter=Q(lots__bloque=False, lots__date_peremption__gte=aujourdhui),
            ),
            0,
        )
    )

    q = request.GET.get("q", "").strip()
    if q:
        medicaments = medicaments.filter(
            Q(nom_commercial__icontains=q) | Q(code_barres__icontains=q)
        )

    categorie_id = request.GET.get("categorie", "")
    if categorie_id.isdigit():
        medicaments = medicaments.filter(categorie_id=int(categorie_id))

    statut = request.GET.get("statut", Medicament.Statut.ACTIF)
    if statut in Medicament.Statut.values:
        medicaments = medicaments.filter(statut=statut)
    else:
        statut = ""  # tous

    tri = request.GET.get("tri", "nom")
    if tri not in TRIS_MEDICAMENTS:
        tri = "nom"
    medicaments = medicaments.order_by(TRIS_MEDICAMENTS[tri], "id")

    page, querystring = _paginer(request, medicaments)
    return render(request, "medicaments/liste.html", {
        "page": page,
        "querystring": querystring,
        "q": q,
        "categorie_id": categorie_id,
        "categories": Categorie.objects.all(),
        "statut": statut,
        "statuts": Medicament.Statut.choices,
        "tri": tri,
        "tris": LIBELLES_TRI,
    })


def detail_medicament(request, pk):
    medicament = get_object_or_404(Medicament.objects.select_related("categorie"), pk=pk)
    return render(request, "medicaments/detail.html", {
        "medicament": medicament,
        "lots": medicament.lots.all(),
    })


def creer_medicament(request):
    form = MedicamentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        medicament = form.save()
        messages.success(request, f"Le médicament « {medicament} » a été ajouté.")
        return redirect("medicaments:detail", pk=medicament.pk)
    return render(request, "medicaments/formulaire_medicament.html", {
        "form": form, "titre": "Ajouter un médicament",
    })


def modifier_medicament(request, pk):
    medicament = get_object_or_404(Medicament, pk=pk)
    form = MedicamentForm(request.POST or None, request.FILES or None, instance=medicament)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Le médicament « {medicament} » a été modifié.")
        return redirect("medicaments:detail", pk=medicament.pk)
    return render(request, "medicaments/formulaire_medicament.html", {
        "form": form, "titre": f"Modifier {medicament}", "medicament": medicament,
    })


def supprimer_medicament(request, pk):
    """Supprime si l'historique n'est pas compromis, sinon archive (RG10)."""
    medicament = get_object_or_404(Medicament, pk=pk)
    historique = medicament.a_historique()
    if request.method == "POST":
        nom = str(medicament)
        if historique:
            medicament.statut = Medicament.Statut.ARCHIVE
            medicament.save(update_fields=["statut"])
            messages.warning(
                request,
                f"« {nom} » a un historique (lots, achats ou ventes) : il a été archivé, pas supprimé.",
            )
            return redirect("medicaments:detail", pk=medicament.pk)
        medicament.delete()
        messages.success(request, f"Le médicament « {nom} » a été supprimé.")
        return redirect("medicaments:liste")
    return render(request, "medicaments/confirmer_suppression_medicament.html", {
        "medicament": medicament, "historique": historique,
    })


# ----------------------------------------------------------------- Catégories

def liste_categories(request):
    categories = Categorie.objects.annotate(nb_medicaments=Count("medicaments")).order_by("nom")
    q = request.GET.get("q", "").strip()
    if q:
        categories = categories.filter(nom__icontains=q)
    page, querystring = _paginer(request, categories)
    return render(request, "medicaments/categories_liste.html", {
        "page": page, "querystring": querystring, "q": q,
    })


def creer_categorie(request):
    form = CategorieForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        categorie = form.save()
        messages.success(request, f"La catégorie « {categorie} » a été ajoutée.")
        return redirect("medicaments:categories")
    return render(request, "medicaments/formulaire_categorie.html", {
        "form": form, "titre": "Ajouter une catégorie",
    })


def modifier_categorie(request, pk):
    categorie = get_object_or_404(Categorie, pk=pk)
    form = CategorieForm(request.POST or None, instance=categorie)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"La catégorie « {categorie} » a été modifiée.")
        return redirect("medicaments:categories")
    return render(request, "medicaments/formulaire_categorie.html", {
        "form": form, "titre": f"Modifier la catégorie {categorie}",
    })


def supprimer_categorie(request, pk):
    categorie = get_object_or_404(Categorie, pk=pk)
    utilisee = categorie.medicaments.exists()
    if request.method == "POST":
        if utilisee:
            messages.error(
                request,
                f"La catégorie « {categorie} » est utilisée par des médicaments : suppression impossible.",
            )
        else:
            nom = str(categorie)
            categorie.delete()
            messages.success(request, f"La catégorie « {nom} » a été supprimée.")
        return redirect("medicaments:categories")
    return render(request, "medicaments/confirmer_suppression_categorie.html", {
        "categorie": categorie, "utilisee": utilisee,
    })
