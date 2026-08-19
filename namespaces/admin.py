from django.contrib import admin

from .models import Namespace


@admin.register(Namespace)
class NamespaceAdmin(admin.ModelAdmin):
    list_display = ["name", "cluster", "status", "created_at"]
    list_filter = ["status", "cluster"]
    search_fields = ["name"]
