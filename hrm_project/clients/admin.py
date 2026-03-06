from django.contrib import admin
from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'domain', 'created_at', 'enabled_addons')
    search_fields = ('name', 'domain')
    readonly_fields = ('created_at',)

