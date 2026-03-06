from rest_framework import serializers
from django.contrib.auth.models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import re
from .models import UserProfile, ClientPermissionGroup


STATIC_PERMISSION_KEYS = {
    'employees.view', 'employees.create', 'employees.edit', 'employees.delete',
    'attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete',
    'custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete',
    'dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete',
}

LEGACY_PERMISSION_MAP = {
    'employees': ['employees.view', 'employees.create', 'employees.edit', 'employees.delete'],
    'attendance': ['attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete'],
    'custom_fields': ['custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete'],
    'dynamic_models': ['dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete'],
}


def normalize_permission_keys(values):
    cleaned = []
    for item in values or []:
        key = str(item).strip()
        if not key:
            continue
        if key in LEGACY_PERMISSION_MAP:
            for expanded in LEGACY_PERMISSION_MAP[key]:
                if expanded not in cleaned:
                    cleaned.append(expanded)
            continue
        if key in STATIC_PERMISSION_KEYS or re.fullmatch(r'dynamic_model\.\d+\.(view|create|edit|delete)', key):
            if key not in cleaned:
                cleaned.append(key)
            continue
        raise serializers.ValidationError(f'Invalid permission: {key}')
    return cleaned


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    module_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    permission_group_name = serializers.CharField(source='permission_group.name', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = (
            'id', 'user', 'client', 'role', 'role_display',
            'module_permissions', 'permission_group', 'permission_group_name', 'created_at'
        )
        read_only_fields = ('id', 'created_at')

    def validate_module_permissions(self, value):
        return normalize_permission_keys(value)


class ClientPermissionGroupSerializer(serializers.ModelSerializer):
    module_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClientPermissionGroup
        fields = ('id', 'client', 'name', 'module_permissions', 'user_count', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_module_permissions(self, value):
        return normalize_permission_keys(value)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom token serializer that includes user profile info"""
    
    def validate(self, attrs):
        request = self.context.get('request')
        client_id = request.data.get('client_id') if request else None
        login_mode = request.data.get('login_mode') if request else None

        data = super().validate(attrs)
        
        user = self.user
        try:
            profile = user.profile

            # Superadmin login does not require selecting a client.
            if login_mode == 'superadmin':
                if profile.role != 'superadmin' and not user.is_superuser:
                    raise serializers.ValidationError(
                        {'detail': 'This account is not a superadmin.'}
                    )
                data['client_id'] = None
                data['role'] = 'superadmin'
                data['user_id'] = user.id
                data['username'] = user.username
                data['module_permissions'] = list(STATIC_PERMISSION_KEYS)
                return data

            # Client-admin login requires a selected client.
            if not client_id:
                raise serializers.ValidationError({'client_id': 'This field is required.'})
            try:
                client_id = int(client_id)
            except (TypeError, ValueError):
                raise serializers.ValidationError({'client_id': 'Invalid client id.'})

            if profile.client_id != client_id:
                raise serializers.ValidationError(
                    {'detail': 'Invalid credentials for selected client.'}
                )
            data['client_id'] = profile.client_id if profile.client else None
            data['role'] = profile.role
            data['user_id'] = user.id
            data['username'] = user.username
            group_permissions = normalize_permission_keys(profile.permission_group.module_permissions or []) if profile.permission_group else []
            data['module_permissions'] = (
                list(STATIC_PERMISSION_KEYS)
                if profile.role == 'admin' else (group_permissions or normalize_permission_keys(profile.module_permissions or []))
            )
            data['permission_group'] = profile.permission_group_id
        except UserProfile.DoesNotExist:
            # Allow Django superusers even if profile row is missing.
            if login_mode == 'superadmin' and user.is_superuser:
                data['client_id'] = None
                data['role'] = 'superadmin'
                data['user_id'] = user.id
                data['username'] = user.username
                data['module_permissions'] = list(STATIC_PERMISSION_KEYS)
                return data
            raise serializers.ValidationError({'detail': 'User profile not found.'})
        
        return data

