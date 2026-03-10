from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from .models import CompanyPolicy
from .serializers import CompanyPolicySerializer


class _PolicyAccessMixin:
    def _profile(self):
        try:
            return self.request.user.profile
        except Exception:
            return None

    def _is_superadmin(self):
        profile = self._profile()
        return self.request.user.is_superuser or bool(profile and profile.role == 'superadmin')

    def _client_id_from_auth(self):
        auth = getattr(self.request, 'auth', None)
        try:
            return auth.get('client_id') if auth is not None else None
        except Exception:
            return None


class CompanyPolicyViewSet(_PolicyAccessMixin, viewsets.ModelViewSet):
    serializer_class = CompanyPolicySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'is_active', 'category']
    search_fields = ['title', 'category', 'content']
    ordering_fields = ['title', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = CompanyPolicy.objects.select_related('client', 'created_by')
        if self._is_superadmin():
            return qs
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id:
            return CompanyPolicy.objects.none()
        return qs.filter(client_id=client_id)

    def perform_create(self, serializer):
        user = self.request.user
        if self._is_superadmin():
            if not serializer.validated_data.get('client'):
                raise PermissionDenied('Client is required for superadmin.')
            serializer.save(created_by=user)
            return
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id:
            raise PermissionDenied('User profile not found.')
        serializer.save(client_id=client_id, created_by=user)

    def perform_update(self, serializer):
        instance = serializer.instance
        if self._is_superadmin():
            serializer.save(client_id=instance.client_id)
            return
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id or client_id != instance.client_id:
            raise PermissionDenied('Not allowed.')
        serializer.save(client_id=instance.client_id)

    def perform_destroy(self, instance):
        if self._is_superadmin():
            instance.delete()
            return
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id or client_id != instance.client_id:
            raise PermissionDenied('Not allowed.')
        instance.delete()
