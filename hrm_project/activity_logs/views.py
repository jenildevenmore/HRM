from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from employees.models import Employee
from .models import ActivityLog
from .serializers import ActivityLogSerializer


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['action', 'module', 'actor', 'actor_role', 'status_code']
    search_fields = [
        'path',
        'module',
        'actor__username',
        'actor__first_name',
        'actor__last_name',
        'actor__email',
    ]
    ordering_fields = ['created_at', 'status_code']

    def _profile(self):
        try:
            return self.request.user.profile
        except Exception:
            return None

    def _is_superadmin(self):
        profile = self._profile()
        return self.request.user.is_superuser or bool(profile and profile.role == 'superadmin')

    def get_queryset(self):
        qs = ActivityLog.objects.select_related('client', 'actor')
        if self._is_superadmin():
            return qs

        profile = self._profile()
        if not profile or not profile.client_id:
            return ActivityLog.objects.none()

        # Client admin can view all for client.
        if profile.role == 'admin':
            return qs.filter(client_id=profile.client_id)

        # Manager/HR can view client logs.
        # Visibility in UI is still controlled by add-on + permission.
        if profile.role in ('employee',):
            return qs.filter(client_id=profile.client_id)

        return ActivityLog.objects.none()

    def _can_employee_view_logs(self, profile):
        mapped = Employee.objects.filter(
            client_id=profile.client_id,
            email__iexact=(self.request.user.email or ''),
        ).only('role').first()
        return bool(mapped and mapped.role in (Employee.ROLE_HR, Employee.ROLE_MANAGER))

    def list(self, request, *args, **kwargs):
        profile = self._profile()
        if not self._is_superadmin():
            if not profile:
                raise PermissionDenied('User profile not found.')
            if profile.role == 'employee' and not self._can_employee_view_logs(profile):
                raise PermissionDenied('Only HR/Manager can view activity logs.')
            if profile.role not in ('admin', 'employee'):
                raise PermissionDenied('Not allowed.')
        return super().list(request, *args, **kwargs)
