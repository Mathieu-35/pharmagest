from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from utilisateurs import audit
from utilisateurs.decorators import permission_requise

from .forms import ClientForm
from .models import Client

PAR_PAGE = 10


@permission_requise("clients.view_client")
def liste_clients(request):
    clients = Client.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        clients = clients.filter(Q(nom__icontains=q) | Q(telephone__icontains=q))
    statut = request.GET.get("statut", "actif")
    if statut == "actif":
        clients = clients.filter(actif=True)
    elif statut == "inactif":
        clients = clients.filter(actif=False)
    else:
        statut = "tous"
    page = Paginator(clients, PAR_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "clients/liste.html", {
        "page": page, "q": q, "statut": statut, "querystring": params.urlencode(),
    })


@permission_requise("clients.view_client")
def detail_client(request, pk):
    client = get_object_or_404(Client, pk=pk)
    ventes = client.ventes.select_related("vendeur").prefetch_related("lignes", "paiements")
    return render(request, "clients/detail.html", {"client": client, "ventes": ventes})


@permission_requise("clients.add_client")
def creer_client(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        audit.enregistrer(request.user, "Client ajouté", client)
        messages.success(request, f"Le client « {client} » a été ajouté.")
        return redirect("clients:detail", pk=client.pk)
    return render(request, "clients/formulaire.html", {"form": form, "titre": "Ajouter un client"})


@permission_requise("clients.change_client")
def modifier_client(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.enregistrer(request.user, "Client modifié", client)
        messages.success(request, f"Le client « {client} » a été modifié.")
        return redirect("clients:detail", pk=client.pk)
    return render(request, "clients/formulaire.html", {
        "form": form, "titre": f"Modifier {client}", "client": client,
    })


@permission_requise("clients.change_client")
@require_POST
def basculer_activation(request, pk):
    client = get_object_or_404(Client, pk=pk)
    client.actif = not client.actif
    client.save(update_fields=["actif"])
    action = "Client activé" if client.actif else "Client désactivé"
    audit.enregistrer(request.user, action, client)
    messages.success(request, f"{action} : « {client} ».")
    return redirect("clients:detail", pk=client.pk)
