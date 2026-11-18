from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from rapports.views import tableau_de_bord

urlpatterns = [
    path("admin/", admin.site.urls),
    path("medicaments/", include("medicaments.urls")),
    path("utilisateurs/", include("utilisateurs.urls")),
    path("fournisseurs/", include("fournisseurs.urls")),
    path("achats/", include("achats.urls")),
    path("stock/", include("stock.urls")),
    path("ventes/", include("ventes.urls")),
    path("clients/", include("clients.urls")),
    path("rapports/", include("rapports.urls")),
    path("", tableau_de_bord, name="accueil"),
]

# Service des photos en développement uniquement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
