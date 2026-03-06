from django.contrib import admin
from .models import UserProfile, ClientPermissionGroup


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'client', 'role', 'permission_group', 'created_at')
    list_filter = ('role', 'client', 'permission_group', 'created_at')
    search_fields = ('user__username', 'user__email', 'client__name')
    raw_id_fields = ('user', 'client', 'permission_group')


@admin.register(ClientPermissionGroup)
class ClientPermissionGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'created_at')
    list_filter = ('client', 'created_at')
    search_fields = ('name', 'client__name')

