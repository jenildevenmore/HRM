from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.utils.text import slugify
import re
from .models import Client, ClientRole
from .services import build_schema_name, provision_client_schema


class ClientSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    ALLOWED_ADDONS = {
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
        'role_management',
        'shift_management',
        'bank_management',
    }

    class Meta:
        model = Client
        fields = (
            'id',
            'name',
            'domain',
            'password',
            'schema_name',
            'schema_provisioned',
            'enabled_addons',
            'app_settings',
            'role_limit',
            'created_at',
        )
        read_only_fields = ('id', 'schema_provisioned', 'created_at')

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'This field is required.'})
        return attrs

    def validate_enabled_addons(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('enabled_addons must be a list.')
        cleaned = []
        for addon in value:
            addon_key = str(addon).strip()
            if addon_key not in self.ALLOWED_ADDONS:
                raise serializers.ValidationError(f'Invalid add-on: {addon_key}')
            if addon_key not in cleaned:
                cleaned.append(addon_key)

        # Premium attendance add-ons imply attendance base module.
        if 'attendance_selfie_location' in cleaned and 'attendance_location' not in cleaned:
            cleaned.append('attendance_location')
        if ('attendance_location' in cleaned or 'attendance_selfie_location' in cleaned) and 'attendance' not in cleaned:
            cleaned.append('attendance')

        return cleaned

    def validate_app_settings(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('app_settings must be an object.')
        return value

    def validate_role_limit(self, value):
        if value is None:
            return 0
        if value < 0:
            raise serializers.ValidationError('role_limit must be 0 or greater.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        if not validated_data.get('schema_name'):
            # Auto-derive schema name from domain/name when not provided.
            temp = Client(**validated_data)
            validated_data['schema_name'] = build_schema_name(temp)
        validated_data['password'] = make_password(password)
        client = super().create(validated_data)

        ok, err = provision_client_schema(client)
        if not ok:
            client.delete()
            raise serializers.ValidationError({'schema_name': err})
        return client

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if 'schema_name' in validated_data and validated_data['schema_name'] != instance.schema_name:
            raise serializers.ValidationError({'schema_name': 'schema_name cannot be changed after creation.'})
        if password:
            validated_data['password'] = make_password(password)
        return super().update(instance, validated_data)


class ClientRoleSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )
    base_role_display = serializers.CharField(source='get_base_role_display', read_only=True)

    class Meta:
        model = ClientRole
        fields = (
            'id',
            'client',
            'name',
            'slug',
            'base_role',
            'base_role_display',
            'module_permissions',
            'enabled_addons',
            'is_active',
            'sort_order',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'slug': {'required': False},
            'base_role': {'required': False},
        }

    def _infer_base_role(self, name):
        text = str(name or '').strip().lower()
        if 'manager' in text:
            return ClientRole.BASE_ROLE_MANAGER
        if re.search(r'(^|[^a-z])hr([^a-z]|$)', text) or 'human resource' in text:
            return ClientRole.BASE_ROLE_HR
        return ClientRole.BASE_ROLE_EMPLOYEE

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        profile = getattr(user, 'profile', None) if user else None

        if user and not user.is_superuser:
            if not profile or profile.role not in ('admin', 'superadmin'):
                raise serializers.ValidationError({'detail': 'Only client admin or superadmin can manage roles.'})
            if profile.role == 'admin':
                attrs['client'] = profile.client
            elif not attrs.get('client') and profile and profile.client_id:
                attrs['client'] = profile.client

        client = attrs.get('client') or getattr(self.instance, 'client', None)
        if not client:
            raise serializers.ValidationError({'client': 'This field is required.'})

        if 'role_management' not in (client.enabled_addons or []):
            raise serializers.ValidationError({'client': 'Role Management add-on is disabled for this client.'})

        limit = int(client.role_limit or 0)
        if self.instance is None and limit > 0:
            existing_count = ClientRole.objects.filter(client=client).count()
            if existing_count >= limit:
                raise serializers.ValidationError(
                    {'name': f'Role limit reached. This client can create maximum {limit} roles.'}
                )

        return attrs

    def validate_module_permissions(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('module_permissions must be a list.')
        cleaned = []
        for item in value:
            key = str(item).strip()
            if key and key not in cleaned:
                cleaned.append(key)
        return cleaned

    def validate_enabled_addons(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('enabled_addons must be a list.')
        cleaned = []
        for item in value:
            key = str(item).strip()
            if key and key not in cleaned:
                cleaned.append(key)
        return cleaned

    def validate_slug(self, value):
        cleaned = slugify(value or '')
        if not cleaned:
            raise serializers.ValidationError('Invalid slug.')
        return cleaned

    def create(self, validated_data):
        if not validated_data.get('slug'):
            validated_data['slug'] = slugify(validated_data.get('name', ''))
        validated_data['base_role'] = self._infer_base_role(validated_data.get('name'))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'name' in validated_data:
            validated_data['base_role'] = self._infer_base_role(validated_data.get('name'))
        return super().update(instance, validated_data)
