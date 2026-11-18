from django.urls import path

from . import views

app_name = "achats"

urlpatterns = [
    path("", views.liste_commandes, name="liste"),
    path("nouvelle/", views.creer_commande, name="creer"),
    path("<int:pk>/", views.detail_commande, name="detail"),
    path("<int:pk>/modifier/", views.modifier_commande, name="modifier"),
    path("<int:pk>/valider/", views.valider_commande, name="valider"),
    path("<int:pk>/annuler/", views.annuler_commande, name="annuler"),
    path("<int:pk>/reception/", views.receptionner_commande, name="reception"),
]
