from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from utilisateurs import audit
from utilisateurs.decorators import permission_requise

from .forms import FournisseurForm
from .models import Fournisseur

PAR_PAGE = 10


@permission_requise("fournisseurs.view_fournisseur")
def liste_fournisseurs(request):
    fournisseurs = Fournisseur.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        fournisseurs = fournisseurs.filter(Q(nom__icontains=q) | Q(telephone__icontains=q))
    statut = request.GET.get("statut", "actif")
    if statut == "actif":
        fournisseurs = fournisseurs.filter(actif=True)
    elif statut == "inactif":
        fournisseurs = fournisseurs.filter(actif=False)
    else:
        statut = "tous"
    page = Paginator(fournisseurs, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "fournisseurs/liste.html", {
        "page": page, "q": q, "statut": statut, "querystring": params.urlencode(),
    })


@permission_requise("fournisseurs.view_fournisseur")
def detail_fournisseur(request, pk):
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    commandes = fournisseur.commandes.prefetch_related(
        "lignes", "receptions__lignes__ligne_achat"
    )
    return render(request, "fournisseurs/detail.html", {
        "fournisseur": fournisseur, "commandes": commandes,
    })


@permission_requise("fournisseurs.add_fournisseur")
def creer_fournisseur(request):
    form = FournisseurForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fournisseur = form.save()
        audit.enregistrer(request.user, "Fournisseur ajouté", fournisseur)
        messages.success(request, f"Le fournisseur « {fournisseur} » a été ajouté.")
        return redirect("fournisseurs:detail", pk=fournisseur.pk)
    return render(request, "fournisseurs/formulaire.html", {
        "form": form, "titre": "Ajouter un fournisseur",
    })


@permission_requise("fournisseurs.change_fournisseur")
def modifier_fournisseur(request, pk):
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    form = FournisseurForm(request.POST or None, instance=fournisseur)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.enregistrer(request.user, "Fournisseur modifié", fournisseur)
        messages.success(request, f"Le fournisseur « {fournisseur} » a été modifié.")
        return redirect("fournisseurs:detail", pk=fournisseur.pk)
    return render(request, "fournisseurs/formulaire.html", {
        "form": form, "titre": f"Modifier {fournisseur}", "fournisseur": fournisseur,
    })


@require_POST
@permission_requise("fournisseurs.change_fournisseur")
def basculer_activation(request, pk):
    """Désactive (ou réactive) un fournisseur sans effacer ses anciennes opérations."""
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    fournisseur.actif = not fournisseur.actif
    fournisseur.save(update_fields=["actif"])
    action = "Fournisseur activé" if fournisseur.actif else "Fournisseur désactivé"
    audit.enregistrer(request.user, action, fournisseur)
    messages.success(request, f"{action} : « {fournisseur} ».")
    return redirect("fournisseurs:detail", pk=fournisseur.pk)


@permission_requise("fournisseurs.delete_fournisseur")
def supprimer_fournisseur(request, pk):
    """Supprime seulement un fournisseur sans commande ; sinon il faut le désactiver."""
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    a_historique = fournisseur.commandes.exists()
    if request.method == "POST":
        if a_historique:
            messages.error(
                request,
                f"« {fournisseur} » a des commandes : suppression impossible, désactivez-le.",
            )
            return redirect("fournisseurs:detail", pk=fournisseur.pk)
        nom = str(fournisseur)
        fournisseur.delete()
        audit.enregistrer(request.user, "Fournisseur supprimé", nom)
        messages.success(request, f"Le fournisseur « {nom} » a été supprimé.")
        return redirect("fournisseurs:liste")
    return render(request, "fournisseurs/confirmer_suppression.html", {
        "fournisseur": fournisseur, "a_historique": a_historique,
    })
