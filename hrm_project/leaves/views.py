from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import UserProfile
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
        qs = LeaveType.objects.select_related('client')
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

    def _resolve_approver_user(self, approver_employee):
        if not approver_employee:
            return None
        profile = (
            UserProfile.objects.select_related('user')
            .filter(
                client_id=approver_employee.client_id,
                user__email__iexact=(approver_employee.email or ''),
            )
            .first()
        )
        return profile.user if profile else None

    def _resolve_client_admin_user(self, client_id, fallback_user=None):
        profile = (
            UserProfile.objects.select_related('user')
            .filter(client_id=client_id, role='admin')
            .order_by('id')
            .first()
        )
        if profile and profile.user_id:
            return profile.user
        return fallback_user

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

        requester_profile = profile
        applicant_role = str(getattr(employee, 'role', Employee.ROLE_EMPLOYEE) or Employee.ROLE_EMPLOYEE).lower()
        if (
            requester_profile
            and requester_profile.role == 'admin'
            and str(getattr(employee, 'email', '') or '').strip().lower() == str(getattr(self.request.user, 'email', '') or '').strip().lower()
        ):
            applicant_role = 'admin'

        manager_user = None
        hr_user = None

        if applicant_role == Employee.ROLE_MANAGER:
            if not employee.hr_id:
                raise PermissionDenied('Selected manager has no HR assigned.')
            hr_user = self._resolve_approver_user(employee.hr)
            manager_user = self._resolve_client_admin_user(employee.client_id, fallback_user=self.request.user)
            if not hr_user:
                raise PermissionDenied(
                    f'No user profile found for assigned HR ({employee.hr.email}). '
                    'Create a user account with the same email.'
                )
            if not manager_user:
                raise PermissionDenied('No client admin user found for approval.')
            if manager_user.id == hr_user.id:
                raise PermissionDenied('Client admin and HR approvers must be different users for manager leave.')
        elif applicant_role in (Employee.ROLE_HR, 'admin'):
            manager_user = self._resolve_client_admin_user(employee.client_id, fallback_user=self.request.user)
            if not manager_user:
                raise PermissionDenied('No client admin user found for approval.')
            hr_user = None
        else:
            if not employee.manager_id:
                raise PermissionDenied('Selected employee has no manager assigned.')
            if not employee.hr_id:
                raise PermissionDenied('Selected employee has no HR assigned.')
            manager_user = self._resolve_approver_user(employee.manager)
            hr_user = self._resolve_approver_user(employee.hr)
            if not manager_user:
                raise PermissionDenied(
                    f'No user profile found for assigned manager ({employee.manager.email}). '
                    'Create a user account with the same email.'
                )
            if not hr_user:
                raise PermissionDenied(
                    f'No user profile found for assigned HR ({employee.hr.email}). '
                    'Create a user account with the same email.'
                )
            if manager_user.id == hr_user.id:
                raise PermissionDenied('Assigned manager and HR must be different users.')

        serializer.save(
            client=employee.client,
            applied_by=self.request.user,
            manager=manager_user,
            hr=hr_user,
            manager_status=(LeaveRequest.APPROVAL_PENDING if manager_user else LeaveRequest.APPROVAL_APPROVED),
            hr_status=(LeaveRequest.APPROVAL_PENDING if hr_user else LeaveRequest.APPROVAL_APPROVED),
            status=LeaveRequest.STATUS_PENDING,
            manager_comment='',
            hr_comment='',
            reviewer_comment='',
            approved_by=None,
            approved_at=None,
        )

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

        def _finalize_status():
            review_states = []
            if instance.manager_id:
                review_states.append(instance.manager_status)
            if instance.hr_id:
                review_states.append(instance.hr_status)
            if any(state == LeaveRequest.APPROVAL_REJECTED for state in review_states):
                return LeaveRequest.STATUS_REJECTED
            if review_states and all(state == LeaveRequest.APPROVAL_APPROVED for state in review_states):
                return LeaveRequest.STATUS_APPROVED
            return LeaveRequest.STATUS_PENDING

        if instance.manager_id == request.user.id:
            if instance.manager_status != LeaveRequest.APPROVAL_PENDING:
                return Response({'detail': 'Manager approval is already submitted.'}, status=status.HTTP_400_BAD_REQUEST)
            instance.manager_status = (
                LeaveRequest.APPROVAL_APPROVED
                if new_status == LeaveRequest.STATUS_APPROVED else LeaveRequest.APPROVAL_REJECTED
            )
            instance.manager_comment = reviewer_comment
            instance.status = _finalize_status()
            instance.reviewer_comment = reviewer_comment
            instance.approved_by = request.user
            instance.approved_at = timezone.now()
            instance.save(update_fields=[
                'manager_status', 'manager_comment', 'status',
                'reviewer_comment', 'approved_by', 'approved_at', 'updated_at',
            ])
            return Response(self.get_serializer(instance).data)

        if instance.hr_id == request.user.id:
            if instance.hr_status != LeaveRequest.APPROVAL_PENDING:
                return Response({'detail': 'HR approval is already submitted.'}, status=status.HTTP_400_BAD_REQUEST)
            instance.hr_status = (
                LeaveRequest.APPROVAL_APPROVED
                if new_status == LeaveRequest.STATUS_APPROVED else LeaveRequest.APPROVAL_REJECTED
            )
            instance.hr_comment = reviewer_comment
            instance.status = _finalize_status()
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
        def _format_days_value(value):
            decimal_value = Decimal(str(value or 0))
            if decimal_value == decimal_value.to_integral():
                return int(decimal_value)
            return float(decimal_value)

        if self._is_superadmin():
            employees = Employee.objects.only('id', 'first_name', 'last_name', 'role').all().order_by('first_name', 'last_name')
            leave_types = LeaveType.objects.only('name', 'is_paid', 'max_days_per_year').filter(is_active=True).order_by('name')
        else:
            profile = self._profile()
            if not profile or not profile.client_id:
                return Response([], status=status.HTTP_200_OK)
            base_employees = Employee.objects.only('id', 'first_name', 'last_name', 'role', 'email').filter(client_id=profile.client_id)
            mapped_employee = base_employees.filter(email__iexact=(request.user.email or '')).first()
            if profile.role == 'admin':
                employees = base_employees.order_by('first_name', 'last_name')
            elif mapped_employee and mapped_employee.role in (Employee.ROLE_HR, Employee.ROLE_MANAGER):
                employees = base_employees.order_by('first_name', 'last_name')
            elif mapped_employee:
                employees = base_employees.filter(id=mapped_employee.id).order_by('first_name', 'last_name')
            else:
                employees = Employee.objects.none()
            leave_types = LeaveType.objects.only('name', 'is_paid', 'max_days_per_year').filter(
                client_id=profile.client_id,
                is_active=True,
            ).order_by('name')

        leave_types_list = list(leave_types)
        employees_list = list(employees)
        employee_ids = [emp.id for emp in employees_list]
        leave_type_names = [lt.name for lt in leave_types_list]

        # Aggregate in one query instead of querying per employee x leave type.
        used_totals_map = {}
        if employee_ids and leave_type_names:
            used_totals = (
                LeaveRequest.objects.filter(
                    employee_id__in=employee_ids,
                    status=LeaveRequest.STATUS_APPROVED,
                    leave_type__in=leave_type_names,
                )
                .values('employee_id', 'leave_type')
                .annotate(
                    total=Sum(
                        Case(
                            When(leave_unit=LeaveRequest.UNIT_HOUR, then=Value(Decimal('0'))),
                            When(leave_unit=LeaveRequest.UNIT_HALF_DAY, then=Value(Decimal('0.5'))),
                            default=F('total_days'),
                            output_field=DecimalField(max_digits=10, decimal_places=2),
                        )
                    )
                )
            )
            used_totals_map = {
                (row['employee_id'], row['leave_type']): Decimal(str(row['total'] or 0))
                for row in used_totals
            }

        rows = []
        for employee in employees_list:
            type_rows = []
            for leave_type in leave_types_list:
                used = used_totals_map.get((employee.id, leave_type.name), Decimal('0'))
                total = Decimal(str(leave_type.max_days_per_year or 0))
                available = total - used
                if available < 0:
                    available = Decimal('0')
                type_rows.append({
                    'leave_type': leave_type.name,
                    'is_paid': leave_type.is_paid,
                    'total': _format_days_value(total),
                    'used': _format_days_value(used),
                    'available': _format_days_value(available),
                })
            rows.append({
                'employee_id': employee.id,
                'employee_name': f'{employee.first_name} {employee.last_name}'.strip(),
                'role': employee.role,
                'balances': type_rows,
            })

        return Response(rows, status=status.HTTP_200_OK)
