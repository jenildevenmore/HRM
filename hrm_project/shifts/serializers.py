from rest_framework import serializers

from clients.models import Client
from .models import Shift


class ShiftSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )

    class Meta:
        model = Shift
        fields = (
            'id',
            'client',
            'name',
            'code',
            'start_time',
            'end_time',
            'grace_minutes',
            'is_night_shift',
            'weekly_off',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        validators = []

    def _resolve_client_from_auth(self, request):
        if not request:
            return None
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        try:
            profile = user.profile
            if profile and profile.client_id:
                return profile.client
        except Exception:
            pass

        auth = getattr(request, 'auth', None)
        client_id = None
        try:
            if auth is not None:
                client_id = auth.get('client_id')
        except Exception:
            client_id = None
        if client_id:
            return Client.objects.filter(id=client_id).first()
        return None

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        resolved_client = self._resolve_client_from_auth(request)

        if user and not user.is_superuser and resolved_client:
            attrs['client'] = resolved_client
        elif user and not user.is_superuser and not resolved_client:
            raise serializers.ValidationError({'client': 'Client could not be resolved from your login token.'})

        if not attrs.get('client') and not (user and user.is_superuser):
            raise serializers.ValidationError({'client': 'This field is required.'})

        start_time = attrs.get('start_time') or getattr(self.instance, 'start_time', None)
        end_time = attrs.get('end_time') or getattr(self.instance, 'end_time', None)
        if start_time and end_time and start_time == end_time:
            raise serializers.ValidationError({'end_time': 'End time must be different from start time.'})

        target_client = attrs.get('client') or resolved_client
        target_name = str(attrs.get('name') or getattr(self.instance, 'name', '')).strip()
        if target_client and target_name:
            qs = Shift.objects.filter(client=target_client, name__iexact=target_name)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({'name': 'Shift with this name already exists.'})

        return attrs
