from django.urls import path

from . import views

app_name = "rapports"

urlpatterns = [
    path("", views.liste_rapports, name="liste"),
    # Rapports PDF
    path("pdf/stock/", views.rapport_stock, name="stock"),
    path("pdf/ventes/", views.rapport_ventes, name="ventes"),
    path("pdf/achats/", views.rapport_achats, name="achats"),
    path("pdf/peremptions/", views.rapport_peremptions, name="peremptions"),
    # Documents PDF
    path("documents/vente/<int:pk>/recu/", views.recu_vente, name="recu"),
    path("documents/vente/<int:pk>/facture/", views.facture_vente, name="facture"),
    path("documents/commande/<int:pk>/bon/", views.bon_commande, name="bon_commande"),
    path("documents/reception/<int:pk>/bon/", views.bon_reception, name="bon_reception"),
]
