from django.db.models import Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from employees.models import Employee

from .models import LeaveRequest, LeaveType
from .serializers import LeaveRequestSerializer, LeaveTypeSerializer


class _LeaveAccessMixin:
    def _profile(self):
        try:
            return self.request.user.profile
        except Exception:
            return None

    def _is_superadmin(self):
        profile = self._profile()
        return self.request.user.is_superuser or bool(profile and profile.role == 'superadmin')

    def _is_client_admin(self):
        profile = self._profile()
        return bool(profile and profile.role == 'admin')

    def _client_id_from_auth(self):
        auth = getattr(self.request, 'auth', None)
        try:
            return auth.get('client_id') if auth is not None else None
        except Exception:
            return None


class LeaveTypeViewSet(_LeaveAccessMixin, viewsets.ModelViewSet):
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['name']
    ordering_fields = ['name', 'max_days_per_year', 'created_at']
    filterset_fields = ['is_paid', 'is_active']

    def get_queryset(self):
        qs = LeaveType.objects.all()
        if self._is_superadmin():
            return qs
        profile = self._profile()
        client_id = profile.client_id if profile and profile.client_id else self._client_id_from_auth()
        if not client_id:
            return LeaveType.objects.none()
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


class LeaveRequestViewSet(_LeaveAccessMixin, viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'employee', 'status', 'leave_type', 'start_date', 'end_date',
        'manager', 'hr', 'manager_status', 'hr_status',
    ]
    search_fields = ['leave_type', 'employee__first_name', 'employee__last_name']
    ordering_fields = ['created_at', 'start_date', 'end_date', 'status']

    def get_queryset(self):
        qs = LeaveRequest.objects.select_related(
            'employee', 'client', 'applied_by', 'approved_by', 'manager', 'hr'
        )
        if self._is_superadmin():
            return qs
        profile = self._profile()
        if not profile or not profile.client_id:
            return LeaveRequest.objects.none()
        return qs.filter(client_id=profile.client_id)

    def perform_create(self, serializer):
        employee = serializer.validated_data['employee']
        profile = self._profile()

        if not self._is_superadmin():
            if not profile or not profile.client_id:
                raise PermissionDenied('User profile not found.')
            if employee.client_id != profile.client_id:
                raise PermissionDenied('Employee must belong to your client.')

            manager = serializer.validated_data.get('manager')
            hr = serializer.validated_data.get('hr')
            for label, user_obj in (('manager', manager), ('hr', hr)):
                try:
                    target_profile = user_obj.profile
                except Exception:
                    target_profile = None
                if not target_profile or target_profile.client_id != profile.client_id:
                    raise PermissionDenied(f'{label.title()} must belong to your client.')

        serializer.save(client=employee.client, applied_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.status != LeaveRequest.STATUS_PENDING:
            raise PermissionDenied('Only pending leave requests can be edited.')
        serializer.save()

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        instance = self.get_object()
        new_status = str(request.data.get('status', '')).strip().lower()
        if new_status not in (LeaveRequest.STATUS_APPROVED, LeaveRequest.STATUS_REJECTED):
            return Response({'status': 'Status must be approved or rejected.'}, status=status.HTTP_400_BAD_REQUEST)

        if instance.status != LeaveRequest.STATUS_PENDING:
            return Response({'detail': 'Only pending leave requests can be reviewed.'}, status=status.HTTP_400_BAD_REQUEST)

        reviewer_comment = str(request.data.get('reviewer_comment', '')).strip()
        is_admin_reviewer = self._is_superadmin() or self._is_client_admin()

        if is_admin_reviewer:
            if new_status == LeaveRequest.STATUS_REJECTED:
                instance.manager_status = LeaveRequest.APPROVAL_REJECTED
                instance.hr_status = LeaveRequest.APPROVAL_REJECTED
            else:
                instance.manager_status = LeaveRequest.APPROVAL_APPROVED
                instance.hr_status = LeaveRequest.APPROVAL_APPROVED
            instance.manager_comment = reviewer_comment
            instance.hr_comment = reviewer_comment
            instance.status = new_status
            instance.reviewer_comment = reviewer_comment
            instance.approved_by = request.user
            instance.approved_at = timezone.now()
            instance.save(update_fields=[
                'manager_status', 'hr_status', 'manager_comment', 'hr_comment',
                'status', 'reviewer_comment', 'approved_by', 'approved_at', 'updated_at',
            ])
            return Response(self.get_serializer(instance).data)

        if instance.manager_id == request.user.id:
            if instance.manager_status != LeaveRequest.APPROVAL_PENDING:
                return Response({'detail': 'Manager approval is already submitted.'}, status=status.HTTP_400_BAD_REQUEST)
            instance.manager_status = (
                LeaveRequest.APPROVAL_APPROVED
                if new_status == LeaveRequest.STATUS_APPROVED else LeaveRequest.APPROVAL_REJECTED
            )
            instance.manager_comment = reviewer_comment
            if new_status == LeaveRequest.STATUS_REJECTED:
                instance.status = LeaveRequest.STATUS_REJECTED
                instance.reviewer_comment = reviewer_comment
                instance.approved_by = request.user
                instance.approved_at = timezone.now()
            elif instance.hr_status == LeaveRequest.APPROVAL_APPROVED:
                instance.status = LeaveRequest.STATUS_APPROVED
                instance.reviewer_comment = reviewer_comment
                instance.approved_by = request.user
                instance.approved_at = timezone.now()
            instance.save(update_fields=[
                'manager_status', 'manager_comment', 'status',
                'reviewer_comment', 'approved_by', 'approved_at', 'updated_at',
            ])
            return Response(self.get_serializer(instance).data)

        if instance.hr_id == request.user.id:
            if instance.manager_status != LeaveRequest.APPROVAL_APPROVED:
                return Response({'detail': 'HR can review only after manager approval.'}, status=status.HTTP_400_BAD_REQUEST)
            if instance.hr_status != LeaveRequest.APPROVAL_PENDING:
                return Response({'detail': 'HR approval is already submitted.'}, status=status.HTTP_400_BAD_REQUEST)
            instance.hr_status = (
                LeaveRequest.APPROVAL_APPROVED
                if new_status == LeaveRequest.STATUS_APPROVED else LeaveRequest.APPROVAL_REJECTED
            )
            instance.hr_comment = reviewer_comment
            instance.status = (
                LeaveRequest.STATUS_APPROVED if new_status == LeaveRequest.STATUS_APPROVED
                else LeaveRequest.STATUS_REJECTED
            )
            instance.reviewer_comment = reviewer_comment
            instance.approved_by = request.user
            instance.approved_at = timezone.now()
            instance.save(update_fields=[
                'hr_status', 'hr_comment', 'status',
                'reviewer_comment', 'approved_by', 'approved_at', 'updated_at',
            ])
            return Response(self.get_serializer(instance).data)

        return Response(
            {'detail': 'Only assigned manager or HR can review this leave.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        instance = self.get_object()
        profile = self._profile()
        if not self._is_superadmin():
            if not profile or not profile.client_id:
                return Response({'detail': 'User profile not found.'}, status=status.HTTP_403_FORBIDDEN)
            if instance.client_id != profile.client_id:
                return Response({'detail': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)

        if instance.status != LeaveRequest.STATUS_PENDING:
            return Response({'detail': 'Only pending leave requests can be cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        instance.status = LeaveRequest.STATUS_CANCELLED
        instance.reviewer_comment = str(request.data.get('reviewer_comment', '')).strip()
        instance.approved_by = request.user
        instance.approved_at = timezone.now()
        instance.save(update_fields=['status', 'reviewer_comment', 'approved_by', 'approved_at', 'updated_at'])
        return Response(self.get_serializer(instance).data)

    def perform_destroy(self, instance):
        if not (self._is_superadmin() or self._is_client_admin()):
            raise PermissionDenied('Only admin can delete leave requests.')
        super().perform_destroy(instance)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        profile = self._profile()
        if not self._is_superadmin():
            if not profile or not profile.client_id or instance.client_id != profile.client_id:
                raise PermissionDenied('Not allowed.')
        return super().destroy(request, *args, **kwargs)


class LeaveBalanceView(_LeaveAccessMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if self._is_superadmin():
            employees = Employee.objects.all().order_by('first_name', 'last_name')
            leave_types = LeaveType.objects.filter(is_active=True).order_by('name')
        else:
            profile = self._profile()
            if not profile or not profile.client_id:
                return Response([], status=status.HTTP_200_OK)
            employees = Employee.objects.filter(client_id=profile.client_id).order_by('first_name', 'last_name')
            leave_types = LeaveType.objects.filter(client_id=profile.client_id, is_active=True).order_by('name')

        leave_types_list = list(leave_types)
        rows = []
        for employee in employees:
            type_rows = []
            for leave_type in leave_types_list:
                used = LeaveRequest.objects.filter(
                    employee_id=employee.id,
                    status=LeaveRequest.STATUS_APPROVED,
                    leave_type=leave_type.name,
                ).aggregate(total=Sum('total_days')).get('total') or 0
                total = int(leave_type.max_days_per_year or 0)
                available = total - int(used)
                if available < 0:
                    available = 0
                type_rows.append({
                    'leave_type': leave_type.name,
                    'is_paid': leave_type.is_paid,
                    'total': total,
                    'used': int(used),
                    'available': available,
                })
            rows.append({
                'employee_id': employee.id,
                'employee_name': f'{employee.first_name} {employee.last_name}'.strip(),
                'role': employee.role,
                'balances': type_rows,
            })

        return Response(rows, status=status.HTTP_200_OK)
