from django.contrib import admin

from .models import Cluster


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "created_at"]
    search_fields = ["name", "address"]
    # Deliberately never expose encrypted_token in the admin UI either.
    exclude = ["encrypted_token"]
    readonly_fields = ["created_at", "updated_at"]
