from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from . import audit
from .decorators import permission_requise
from .forms import ChangerMotDePasseForm, UtilisateurForm
from .models import JournalAudit

User = get_user_model()
PAR_PAGE = 15


def _verifier_cible(request, utilisateur):
    """Seul un super-utilisateur peut modifier un super-utilisateur."""
    if utilisateur.is_superuser and not request.user.is_superuser:
        raise PermissionDenied


@permission_requise("auth.view_user")
def liste_utilisateurs(request):
    utilisateurs = User.objects.prefetch_related("groups").order_by("username")
    q = request.GET.get("q", "").strip()
    if q:
        utilisateurs = utilisateurs.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q)
            | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    page = Paginator(utilisateurs, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "utilisateurs/liste.html", {
        "page": page, "q": q, "querystring": params.urlencode(),
    })


@permission_requise("auth.add_user")
def creer_utilisateur(request):
    form = UtilisateurForm(request.POST or None, utilisateur_courant=request.user)
    if request.method == "POST" and form.is_valid():
        utilisateur = form.save()
        roles = ", ".join(g.name for g in utilisateur.groups.all()) or "aucun rôle"
        audit.enregistrer(request.user, "Compte créé", utilisateur.username, f"Rôles : {roles}")
        messages.success(request, f"Le compte « {utilisateur.username} » a été créé.")
        return redirect("utilisateurs:liste")
    return render(request, "utilisateurs/formulaire.html", {
        "form": form, "titre": "Ajouter un utilisateur",
    })


@permission_requise("auth.change_user")
def modifier_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    _verifier_cible(request, utilisateur)
    form = UtilisateurForm(
        request.POST or None, instance=utilisateur, utilisateur_courant=request.user
    )
    if request.method == "POST" and form.is_valid():
        utilisateur = form.save()
        roles = ", ".join(g.name for g in utilisateur.groups.all()) or "aucun rôle"
        audit.enregistrer(request.user, "Compte modifié", utilisateur.username, f"Rôles : {roles}")
        messages.success(request, f"Le compte « {utilisateur.username} » a été modifié.")
        return redirect("utilisateurs:liste")
    return render(request, "utilisateurs/formulaire.html", {
        "form": form, "titre": f"Modifier {utilisateur.username}",
    })


@require_POST
@permission_requise("auth.change_user")
def basculer_activation(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    _verifier_cible(request, utilisateur)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect("utilisateurs:liste")
    utilisateur.is_active = not utilisateur.is_active
    utilisateur.save(update_fields=["is_active"])
    action = "Compte activé" if utilisateur.is_active else "Compte désactivé"
    audit.enregistrer(request.user, action, utilisateur.username)
    messages.success(request, f"{action} : « {utilisateur.username} ».")
    return redirect("utilisateurs:liste")


@permission_requise("utilisateurs.view_journalaudit")
def journal_audit(request):
    entrees = JournalAudit.objects.select_related("utilisateur")
    q = request.GET.get("q", "").strip()
    if q:
        entrees = entrees.filter(
            Q(action__icontains=q) | Q(objet__icontains=q)
            | Q(utilisateur__username__icontains=q)
        )
    page = Paginator(entrees, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "utilisateurs/journal.html", {
        "page": page, "q": q, "querystring": params.urlencode(),
    })


class ChangerMotDePasseView(PasswordChangeView):
    template_name = "utilisateurs/mot_de_passe_changer.html"
    form_class = ChangerMotDePasseForm
    success_url = reverse_lazy("accueil")

    def form_valid(self, form):
        reponse = super().form_valid(form)
        audit.enregistrer(self.request.user, "Mot de passe changé", self.request.user.username)
        messages.success(self.request, "Votre mot de passe a été modifié.")
        return reponse
