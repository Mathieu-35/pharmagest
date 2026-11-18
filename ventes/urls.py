from django.urls import path

from . import views

app_name = "ventes"

urlpatterns = [
    # Caisse
    path("caisse/", views.caisse, name="caisse"),
    path("caisse/rechercher/", views.rechercher, name="rechercher"),
    path("caisse/ajouter/", views.panier_ajouter, name="panier_ajouter"),
    path("caisse/ligne/<int:index>/modifier/", views.panier_modifier, name="panier_modifier"),
    path("caisse/ligne/<int:index>/retirer/", views.panier_retirer, name="panier_retirer"),
    path("caisse/vider/", views.panier_vider, name="panier_vider"),
    path("caisse/valider/", views.valider, name="valider"),
    # Historique et reçu
    path("", views.liste_ventes, name="liste"),
    path("<int:pk>/", views.detail_vente, name="detail"),
    # Paiements
    path("<int:pk>/paiement/", views.paiement_ajouter, name="paiement_ajouter"),
    path("paiement/<int:pk>/confirmer/", views.paiement_confirmer, name="paiement_confirmer"),
    path("paiement/<int:pk>/echec/", views.paiement_echoue, name="paiement_echoue"),
    # Retours et annulation
    path("<int:pk>/retour/", views.retour, name="retour"),
    path("<int:pk>/annuler/", views.annuler, name="annuler"),
]
