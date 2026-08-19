from django.contrib import admin

from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["name", "namespace", "image", "replicas", "status", "created_at"]
    list_filter = ["status", "namespace__cluster"]
    search_fields = ["name", "image"]
