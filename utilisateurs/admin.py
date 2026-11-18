from django.contrib import admin

from .models import JournalAudit


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    """Consultation seule : le journal ne se modifie pas à la main (RG09)."""

    list_display = ("date", "utilisateur", "action", "objet")
    list_filter = ("action",)
    search_fields = ("action", "objet", "detail")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
