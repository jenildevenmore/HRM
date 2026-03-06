from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import Client
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
