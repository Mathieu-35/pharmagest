from django.urls import path

from . import views

app_name = "stock"

urlpatterns = [
    path("", views.stock_disponible, name="disponible"),
    path("lots/", views.liste_lots, name="lots"),
    path("lots/<int:pk>/blocage/", views.basculer_blocage, name="blocage"),
    path("mouvements/", views.liste_mouvements, name="mouvements"),
    path("inventaire/", views.inventaire, name="inventaire"),
]
