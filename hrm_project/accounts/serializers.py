from rest_framework import serializers
from django.contrib.auth.models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import re
from .models import UserProfile, ClientPermissionGroup
from clients.models import Client
from employees.models import Employee


STATIC_PERMISSION_KEYS = {
    'dashboard.view', 'dashboard.create', 'dashboard.edit', 'dashboard.delete',
    'employees.view', 'employees.create', 'employees.edit', 'employees.delete',
    'attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete',
    'leaves.view', 'leaves.create', 'leaves.edit', 'leaves.delete', 'leaves.approve',
    'holidays.view', 'holidays.create', 'holidays.edit', 'holidays.delete',
    'shifts.view', 'shifts.create', 'shifts.edit', 'shifts.delete',
    'bank.view', 'bank.create', 'bank.edit', 'bank.delete',
    'policy.view', 'policy.create', 'policy.edit', 'policy.delete',
    'documents.view', 'documents.create', 'documents.edit', 'documents.delete',
    'import_export.view', 'import_export.import', 'import_export.export',
    'custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete',
    'dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete',
    'activity_logs.view',
}

LEGACY_PERMISSION_MAP = {
    'dashboard': ['dashboard.view', 'dashboard.create', 'dashboard.edit', 'dashboard.delete'],
    'employees': ['employees.view', 'employees.create', 'employees.edit', 'employees.delete'],
    'attendance': ['attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete'],
    'leaves': ['leaves.view', 'leaves.create', 'leaves.edit', 'leaves.delete', 'leaves.approve'],
    'holidays': ['holidays.view', 'holidays.create', 'holidays.edit', 'holidays.delete'],
    'shifts': ['shifts.view', 'shifts.create', 'shifts.edit', 'shifts.delete'],
    'bank': ['bank.view', 'bank.create', 'bank.edit', 'bank.delete'],
    'policy': ['policy.view', 'policy.create', 'policy.edit', 'policy.delete'],
    'documents': ['documents.view', 'documents.create', 'documents.edit', 'documents.delete'],
    'import_export': ['import_export.view', 'import_export.import', 'import_export.export'],
    'custom_fields': ['custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete'],
    'dynamic_models': ['dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete'],
}

ALLOWED_ADDON_KEYS = {
    'custom_fields',
    'dynamic_models',
    'attendance',
    'attendance_location',
    'attendance_selfie_location',
    'leave_management',
    'holidays',
    'payroll',
    'activity_logs',
    'settings',
    'policy',
    'documents',
    'import_export',
    'role_management',
    'shift_management',
    'bank_management',
}


def normalize_addon_keys(values):
    cleaned = []
    for item in values or []:
        key = str(item).strip()
        if not key:
            continue
        if key not in ALLOWED_ADDON_KEYS:
            raise serializers.ValidationError(f'Invalid add-on: {key}')
        if key not in cleaned:
            cleaned.append(key)
    if 'attendance_selfie_location' in cleaned and 'attendance_location' not in cleaned:
        cleaned.append('attendance_location')
    if ('attendance_location' in cleaned or 'attendance_selfie_location' in cleaned) and 'attendance' not in cleaned:
        cleaned.append('attendance')
    return cleaned


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


def resolve_profile_access(profile, user=None):
    user_obj = user or getattr(profile, 'user', None)
    group_permissions = normalize_permission_keys(profile.permission_group.module_permissions or []) if profile.permission_group else []
    group_addons = normalize_addon_keys(profile.permission_group.enabled_addons or []) if profile.permission_group else []
    user_permissions = normalize_permission_keys(profile.module_permissions or [])
    user_addons = normalize_addon_keys(profile.enabled_addons or [])
    client_addons = normalize_addon_keys((profile.client.enabled_addons if profile.client else []) or [])
    employee_row = (
        Employee.objects.select_related('client_role')
        .filter(
            client_id=profile.client_id,
            email__iexact=((getattr(user_obj, 'email', '') or '')),
        )
        .only('id', 'role', 'client_role__module_permissions', 'client_role__enabled_addons')
        .first()
    )
    role_permissions = normalize_permission_keys(
        (employee_row.client_role.module_permissions if employee_row and employee_row.client_role else []) or []
    )
    role_addons = normalize_addon_keys(
        (employee_row.client_role.enabled_addons if employee_row and employee_row.client_role else []) or []
    )

    if profile.role == 'admin':
        resolved_permissions = list(STATIC_PERMISSION_KEYS)
        resolved_addons = client_addons
    else:
        if employee_row and employee_row.client_role:
            resolved_permissions = role_permissions
            resolved_addons = [addon for addon in role_addons if addon in client_addons] if role_addons else []
        elif group_permissions or group_addons:
            resolved_permissions = group_permissions
            resolved_addons = [addon for addon in group_addons if addon in client_addons] if group_addons else []
        else:
            resolved_permissions = user_permissions
            resolved_addons = [addon for addon in user_addons if addon in client_addons] if user_addons else client_addons

    return {
        'module_permissions': resolved_permissions,
        'enabled_addons': resolved_addons,
        'employee_id': employee_row.id if employee_row else None,
        'employee_role': employee_row.role if employee_row else '',
    }


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    employee_id = serializers.SerializerMethodField()
    employee_role = serializers.SerializerMethodField()
    module_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    enabled_addons = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    permission_group_name = serializers.CharField(source='permission_group.name', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = (
            'id', 'user', 'client', 'role', 'role_display',
            'module_permissions', 'enabled_addons', 'permission_group', 'permission_group_name',
            'employee_id', 'employee_role', 'created_at'
        )
        read_only_fields = ('id', 'created_at')

    def validate_module_permissions(self, value):
        return normalize_permission_keys(value)

    def validate_enabled_addons(self, value):
        return normalize_addon_keys(value)

    def get_employee_id(self, obj):
        employee = self._get_employee_row(obj)
        return employee.id if employee else None

    def get_employee_role(self, obj):
        employee = self._get_employee_row(obj)
        return employee.role if employee else ''

    def _get_employee_row(self, obj):
        cache_attr = '_cached_employee_row'
        cached = getattr(obj, cache_attr, None)
        if cached is not None:
            return cached

        employee = (
            Employee.objects.filter(
                client_id=obj.client_id,
                email__iexact=(obj.user.email or ''),
            )
            .only('id', 'role')
            .first()
        )
        setattr(obj, cache_attr, employee or False)
        return employee

    def to_representation(self, instance):
        data = super().to_representation(instance)
        resolved = resolve_profile_access(instance)
        data['module_permissions'] = resolved['module_permissions']
        data['enabled_addons'] = resolved['enabled_addons']
        data['employee_id'] = resolved['employee_id']
        data['employee_role'] = resolved['employee_role']
        return data


class ClientPermissionGroupSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )
    module_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    enabled_addons = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClientPermissionGroup
        fields = ('id', 'client', 'name', 'module_permissions', 'enabled_addons', 'user_count', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_module_permissions(self, value):
        return normalize_permission_keys(value)

    def validate_enabled_addons(self, value):
        return normalize_addon_keys(value)

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        profile = getattr(user, 'profile', None) if user else None

        if user and not user.is_superuser and profile and profile.role == 'admin':
            attrs['client'] = profile.client
            return attrs

        if not attrs.get('client') and not (user and user.is_superuser):
            raise serializers.ValidationError({'client': 'This field is required.'})

        return attrs


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
                data['user_email'] = user.email
                data['module_permissions'] = list(STATIC_PERMISSION_KEYS)
                data['enabled_addons'] = list(ALLOWED_ADDON_KEYS)
                data['employee_id'] = None
                data['employee_role'] = ''
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
            data['user_email'] = user.email
            resolved_access = resolve_profile_access(profile, user=user)
            data['module_permissions'] = resolved_access['module_permissions']
            data['enabled_addons'] = resolved_access['enabled_addons']
            data['permission_group'] = profile.permission_group_id
            data['employee_id'] = resolved_access['employee_id']
            data['employee_role'] = resolved_access['employee_role']
        except UserProfile.DoesNotExist:
            # Allow Django superusers even if profile row is missing.
            if login_mode == 'superadmin' and user.is_superuser:
                data['client_id'] = None
                data['role'] = 'superadmin'
                data['user_id'] = user.id
                data['username'] = user.username
                data['user_email'] = user.email
                data['module_permissions'] = list(STATIC_PERMISSION_KEYS)
                data['enabled_addons'] = list(ALLOWED_ADDON_KEYS)
                data['employee_id'] = None
                data['employee_role'] = ''
                return data
            raise serializers.ValidationError({'detail': 'User profile not found.'})
        
        return data

