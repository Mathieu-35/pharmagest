import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from utilisateurs import audit
from utilisateurs.decorators import permission_requise

from . import services
from .forms import CommandeForm, ReceptionForm, formset_lignes
from .models import CommandeAchat, ReceptionAchat

PAR_PAGE = 10


@permission_requise("achats.view_commandeachat")
def liste_commandes(request):
    commandes = CommandeAchat.objects.select_related("fournisseur", "cree_par").prefetch_related("lignes")
    q = request.GET.get("q", "").strip()
    if q:
        commandes = commandes.filter(fournisseur__nom__icontains=q)
    statut = request.GET.get("statut", "")
    if statut in CommandeAchat.Statut.values:
        commandes = commandes.filter(statut=statut)
    else:
        statut = ""
    page = Paginator(commandes, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "achats/liste.html", {
        "page": page, "q": q, "statut": statut, "statuts": CommandeAchat.Statut.choices,
        "querystring": params.urlencode(),
    })


@permission_requise("achats.view_commandeachat")
def detail_commande(request, pk):
    commande = get_object_or_404(
        CommandeAchat.objects.select_related("fournisseur", "cree_par"), pk=pk
    )
    return render(request, "achats/detail.html", {
        "commande": commande,
        "lignes": commande.lignes.select_related("medicament"),
        "receptions": commande.receptions.select_related("recue_par").prefetch_related(
            "lignes__lot", "lignes__ligne_achat__medicament"),
    })


@permission_requise("achats.add_commandeachat")
def creer_commande(request):
    commande = CommandeAchat(cree_par=request.user)
    FormSet = formset_lignes(extra=5)
    form = CommandeForm(request.POST or None, instance=commande)
    formset = FormSet(request.POST or None, instance=commande)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            commande = form.save()
            formset.instance = commande
            formset.save()
        audit.enregistrer(request.user, "Commande créée", commande, f"Montant : {commande.montant_total}")
        messages.success(request, f"La commande {commande.numero} a été enregistrée en brouillon.")
        return redirect("achats:detail", pk=commande.pk)
    return render(request, "achats/formulaire.html", {
        "form": form, "formset": formset, "titre": "Nouvelle commande d'achat",
    })


@permission_requise("achats.change_commandeachat")
def modifier_commande(request, pk):
    commande = get_object_or_404(CommandeAchat, pk=pk)
    if not commande.est_modifiable:
        messages.error(request, "Seule une commande en brouillon peut être modifiée.")
        return redirect("achats:detail", pk=commande.pk)
    FormSet = formset_lignes(extra=3)
    form = CommandeForm(request.POST or None, instance=commande)
    formset = FormSet(request.POST or None, instance=commande)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
        audit.enregistrer(request.user, "Commande modifiée", commande, f"Montant : {commande.montant_total}")
        messages.success(request, f"La commande {commande.numero} a été modifiée.")
        return redirect("achats:detail", pk=commande.pk)
    return render(request, "achats/formulaire.html", {
        "form": form, "formset": formset, "titre": f"Modifier la commande {commande.numero}",
        "commande": commande,
    })


def _action_commande(request, pk, *, fonction, titre, message, bouton, classe, succes):
    """Valider / annuler : page de confirmation (GET), puis exécution (POST)."""
    commande = get_object_or_404(CommandeAchat, pk=pk)
    if request.method == "POST":
        try:
            fonction(commande.pk, request.user)
        except services.ErreurAchat as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, succes.format(numero=commande.numero))
        return redirect("achats:detail", pk=commande.pk)
    return render(request, "achats/confirmer.html", {
        "commande": commande, "titre": titre, "message": message,
        "bouton": bouton, "classe": classe,
    })


@permission_requise("achats.change_commandeachat")
def valider_commande(request, pk):
    return _action_commande(
        request, pk, fonction=services.valider_commande,
        titre="Valider la commande",
        message="Une fois validée, la commande n'est plus modifiable et peut être réceptionnée. Le stock n'augmente qu'à la réception.",
        bouton="Valider la commande", classe="btn-success",
        succes="La commande {numero} est validée (commandée).",
    )


@permission_requise("achats.change_commandeachat")
def annuler_commande(request, pk):
    return _action_commande(
        request, pk, fonction=services.annuler_commande,
        titre="Annuler la commande",
        message="La commande sera annulée. Elle reste consultable dans l'historique.",
        bouton="Annuler la commande", classe="btn-danger",
        succes="La commande {numero} est annulée.",
    )


@permission_requise("achats.add_receptionachat")
def receptionner_commande(request, pk):
    commande = get_object_or_404(CommandeAchat, pk=pk)

    # Double envoi du même formulaire : on le reconnaît avant tout autre contrôle (RG05)
    if request.method == "POST":
        try:
            deja = ReceptionAchat.objects.filter(
                jeton=uuid.UUID(request.POST.get("jeton", "")), commande=commande
            ).first()
        except ValueError:
            deja = None
        if deja:
            messages.info(request, f"La réception {deja} avait déjà été enregistrée : rien n'a été ajouté une seconde fois.")
            return redirect("achats:detail", pk=commande.pk)

    if not commande.est_receptionnable:
        messages.error(request, "Cette commande n'est pas réceptionnable (à valider, terminée ou annulée).")
        return redirect("achats:detail", pk=commande.pk)

    lignes = [l for l in commande.lignes.select_related("medicament") if l.quantite_a_recevoir > 0]
    form = ReceptionForm(request.POST or None, lignes=lignes)

    if request.method == "POST":
        try:
            jeton = uuid.UUID(request.POST.get("jeton", ""))
        except ValueError:
            jeton = None
            form.add_error(None, "Formulaire expiré : rechargez la page et recommencez.")
        if jeton and form.is_valid():
            try:
                reception, creee = services.receptionner(
                    commande.pk, request.user, jeton, form.cleaned_data["saisies"]
                )
            except services.ErreurAchat as erreur:
                form.add_error(None, str(erreur))
            else:
                if creee:
                    messages.success(request, f"Réception {reception} enregistrée : le stock a été mis à jour.")
                else:
                    messages.info(request, f"La réception {reception} avait déjà été enregistrée : rien n'a été ajouté une seconde fois.")
                return redirect("achats:detail", pk=commande.pk)
        jeton_formulaire = request.POST.get("jeton", "")
    else:
        jeton_formulaire = str(uuid.uuid4())

    return render(request, "achats/reception.html", {
        "commande": commande, "form": form, "jeton": jeton_formulaire,
        "champs": form.champs_par_ligne(),
    })
