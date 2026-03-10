from django.contrib import admin
from .models import Client, ClientRole


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'domain', 'role_limit', 'created_at', 'enabled_addons')
    search_fields = ('name', 'domain')
    readonly_fields = ('created_at',)


@admin.register(ClientRole)
class ClientRoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'name', 'base_role', 'is_active', 'sort_order')
    list_filter = ('base_role', 'is_active')
    search_fields = ('name', 'slug', 'client__name', 'client__domain')

