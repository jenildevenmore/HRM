from rest_framework import serializers

from clients.models import Client
from .models import CompanyPolicy


class CompanyPolicySerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = CompanyPolicy
        fields = (
            'id',
            'client',
            'title',
            'category',
            'content',
            'image_url',
            'document_url',
            'is_active',
            'created_by',
            'created_by_username',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_by', 'created_at', 'updated_at')
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

        title = str(attrs.get('title') or getattr(self.instance, 'title', '')).strip()
        if not title:
            raise serializers.ValidationError({'title': 'This field is required.'})

        target_client = attrs.get('client') or resolved_client
        if target_client:
            qs = CompanyPolicy.objects.filter(client=target_client, title__iexact=title)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({'title': 'Policy with this title already exists.'})
        return attrs
