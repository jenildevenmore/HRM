from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from .models import Holiday
from .serializers import HolidaySerializer


class _HolidayAccessMixin:
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


class HolidayViewSet(_HolidayAccessMixin, viewsets.ModelViewSet):
    serializer_class = HolidaySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_paid', 'is_active', 'holiday_type', 'start_date', 'end_date']
    search_fields = ['name', 'holiday_type', 'description']
    ordering_fields = ['start_date', 'end_date', 'name', 'created_at']

    def get_queryset(self):
        qs = Holiday.objects.select_related('client')
        if self._is_superadmin():
            return qs
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id:
            return Holiday.objects.none()
        return qs.filter(client_id=client_id)

    def perform_create(self, serializer):
        if self._is_superadmin():
            if not serializer.validated_data.get('client'):
                raise PermissionDenied('Client is required for superadmin.')
            serializer.save()
            return
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id:
            raise PermissionDenied('User profile not found.')
        serializer.save(client_id=client_id)

    def perform_update(self, serializer):
        instance = serializer.instance
        if self._is_superadmin():
            serializer.save()
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
