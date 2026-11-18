from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("medicaments/", include("medicaments.urls")),
    path("utilisateurs/", include("utilisateurs.urls")),
    path("", login_required(TemplateView.as_view(template_name="accueil.html")), name="accueil"),
]

# Service des photos en développement uniquement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
