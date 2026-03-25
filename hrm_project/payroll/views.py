import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import AttendanceRecord
from employees.models import Employee
from leaves.models import LeaveRequest, LeaveType

from .models import EmployeeCompensation, PayrollPolicy
from .serializers import EmployeeCompensationSerializer, PayrollPolicySerializer


class _PayrollAccessMixin:
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

    def _client_id(self):
        profile = self._profile()
        if profile and profile.client_id:
            return profile.client_id
        return self._client_id_from_auth()

    def _can_manage_payroll(self):
        return self._is_superadmin() or self._is_client_admin()


class PayrollPolicyViewSet(_PayrollAccessMixin, viewsets.ModelViewSet):
    serializer_class = PayrollPolicySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PayrollPolicy.objects.select_related('client')
        if self._is_superadmin():
            return qs
        client_id = self._client_id()
        if not client_id:
            return PayrollPolicy.objects.none()
        return qs.filter(client_id=client_id)

    def create(self, request, *args, **kwargs):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage payroll policy.')
        payload = request.data.copy()
        if not self._is_superadmin():
            payload['client'] = self._client_id()
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage payroll policy.')
        if self._is_superadmin():
            serializer.save()
            return
        client_id = self._client_id()
        if not client_id:
            raise PermissionDenied('User profile not found.')
        serializer.save(client_id=client_id)

    def perform_update(self, serializer):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage payroll policy.')
        instance = serializer.instance
        if not self._is_superadmin() and self._client_id() != instance.client_id:
            raise PermissionDenied('Not allowed for this client.')
        serializer.save(client_id=instance.client_id)

    def perform_destroy(self, instance):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage payroll policy.')
        if not self._is_superadmin() and self._client_id() != instance.client_id:
            raise PermissionDenied('Not allowed for this client.')
        instance.delete()


class EmployeeCompensationViewSet(_PayrollAccessMixin, viewsets.ModelViewSet):
    serializer_class = EmployeeCompensationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = EmployeeCompensation.objects.select_related('employee', 'employee__client', 'shift')
        if self._is_superadmin():
            return qs
        client_id = self._client_id()
        if not client_id:
            return EmployeeCompensation.objects.none()
        return qs.filter(employee__client_id=client_id)

    def perform_create(self, serializer):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage compensation.')
        employee = serializer.validated_data['employee']
        if not self._is_superadmin() and employee.client_id != self._client_id():
            raise PermissionDenied('Employee must belong to your client.')
        serializer.save()

    def perform_update(self, serializer):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage compensation.')
        employee = serializer.validated_data.get('employee', serializer.instance.employee)
        if not self._is_superadmin() and employee.client_id != self._client_id():
            raise PermissionDenied('Employee must belong to your client.')
        serializer.save()

    def perform_destroy(self, instance):
        if not self._can_manage_payroll():
            raise PermissionDenied('Only superadmin/client admin can manage compensation.')
        if not self._is_superadmin() and instance.employee.client_id != self._client_id():
            raise PermissionDenied('Not allowed for this client.')
        instance.delete()


class PayrollReportView(_PayrollAccessMixin, APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _attendance_record_hours(record):
        check_in = getattr(record, 'check_in', None)
        check_out = getattr(record, 'check_out', None)
        if not check_in or not check_out:
            return Decimal('0')

        check_in_dt = datetime.combine(date.today(), check_in)
        check_out_dt = datetime.combine(date.today(), check_out)
        if check_out_dt < check_in_dt:
            check_out_dt = check_out_dt + timedelta(days=1)
        total_seconds = Decimal((check_out_dt - check_in_dt).total_seconds())
        if total_seconds <= 0:
            return Decimal('0')

        break_seconds = Decimal('0')
        breaks_qs = getattr(record, 'breaks', None)
        if breaks_qs is not None:
            for br in breaks_qs.all():
                if not br.break_in or not br.break_out:
                    continue
                br_in_dt = datetime.combine(date.today(), br.break_in)
                br_out_dt = datetime.combine(date.today(), br.break_out)
                if br_out_dt < br_in_dt:
                    br_out_dt = br_out_dt + timedelta(days=1)
                delta_seconds = Decimal((br_out_dt - br_in_dt).total_seconds())
                if delta_seconds > 0:
                    break_seconds += delta_seconds

        net_seconds = total_seconds - break_seconds
        if net_seconds <= 0:
            return Decimal('0')
        return net_seconds / Decimal('3600')

    def _resolve_month(self, request):
        today = date.today()
        year = int(request.query_params.get('year') or today.year)
        month = int(request.query_params.get('month') or today.month)
        if month < 1 or month > 12:
            raise PermissionDenied('month must be between 1 and 12.')
        _, last_day = calendar.monthrange(year, month)
        return year, month, date(year, month, 1), date(year, month, last_day)

    def get(self, request):
        year, month, month_start, month_end = self._resolve_month(request)

        profile = self._profile()
        if not self._is_superadmin() and not profile:
            return Response([], status=status.HTTP_200_OK)

        if self._is_superadmin():
            client_id = request.query_params.get('client')
            if client_id:
                client_id = int(client_id)
        else:
            client_id = profile.client_id

        employees_qs = Employee.objects.select_related('client', 'compensation', 'compensation__shift')
        if client_id:
            employees_qs = employees_qs.filter(client_id=client_id)

        requested_employee_id = request.query_params.get('employee')
        if requested_employee_id:
            employees_qs = employees_qs.filter(id=int(requested_employee_id))

        # For employee login, force self-only report by email mapping.
        if not self._is_superadmin() and profile and profile.role not in ('admin',):
            mapped_employee = employees_qs.filter(email__iexact=(request.user.email or '')).first()
            if mapped_employee and mapped_employee.role in (Employee.ROLE_HR, Employee.ROLE_MANAGER):
                pass
            elif mapped_employee:
                employees_qs = employees_qs.filter(id=mapped_employee.id)
            else:
                employees_qs = Employee.objects.none()

        employees = list(employees_qs.order_by('first_name', 'last_name'))
        employee_ids = [emp.id for emp in employees]

        if not employees:
            return Response([], status=status.HTTP_200_OK)

        policy_by_client = {}
        for policy in PayrollPolicy.objects.filter(client_id__in=list({e.client_id for e in employees})):
            policy_by_client[policy.client_id] = policy

        # Pull attendance records once and aggregate hours per employee.
        hours_by_employee = {emp_id: Decimal('0') for emp_id in employee_ids}
        present_days_by_employee = {emp_id: set() for emp_id in employee_ids}
        attendance_qs = AttendanceRecord.objects.filter(
            employee_id__in=employee_ids,
            attendance_date__gte=month_start,
            attendance_date__lte=month_end,
        ).exclude(status=AttendanceRecord.STATUS_ABSENT).prefetch_related('breaks')
        if client_id:
            attendance_qs = attendance_qs.filter(client_id=client_id)

        for rec in attendance_qs.only('employee_id', 'attendance_date', 'status', 'check_in', 'check_out'):
            att_date = rec.attendance_date
            worked_hours = self._attendance_record_hours(rec)
            if worked_hours <= 0:
                continue
            hours_by_employee[rec.employee_id] = hours_by_employee[rec.employee_id] + worked_hours
            present_days_by_employee[rec.employee_id].add(att_date)

        # Approved paid leave should contribute to payroll (days/hours).
        paid_leave_days_by_employee = {emp_id: set() for emp_id in employee_ids}
        paid_leave_half_days_by_employee = {emp_id: set() for emp_id in employee_ids}
        paid_leave_hours_by_employee = {emp_id: Decimal('0') for emp_id in employee_ids}
        paid_type_names_by_client = {}
        for leave_type in LeaveType.objects.filter(
            client_id__in=list({e.client_id for e in employees}),
            is_active=True,
            is_paid=True,
        ).only('client_id', 'name'):
            paid_type_names_by_client.setdefault(leave_type.client_id, set()).add(str(leave_type.name or ''))

        leave_rows = LeaveRequest.objects.filter(
            employee_id__in=employee_ids,
            status=LeaveRequest.STATUS_APPROVED,
            start_date__lte=month_end,
            end_date__gte=month_start,
        ).only('employee_id', 'start_date', 'end_date', 'leave_unit', 'leave_hours', 'leave_type', 'client_id')

        for leave in leave_rows:
            paid_types = paid_type_names_by_client.get(leave.client_id, set())
            if str(leave.leave_type or '') not in paid_types:
                continue

            leave_unit = str(getattr(leave, 'leave_unit', LeaveRequest.UNIT_DAY) or LeaveRequest.UNIT_DAY).lower()
            if leave_unit == LeaveRequest.UNIT_HOUR:
                leave_hours = Decimal(str(getattr(leave, 'leave_hours', 0) or 0))
                if leave_hours > 0:
                    paid_leave_hours_by_employee[leave.employee_id] += leave_hours
                continue

            overlap_start = leave.start_date if leave.start_date >= month_start else month_start
            overlap_end = leave.end_date if leave.end_date <= month_end else month_end
            target_set = (
                paid_leave_half_days_by_employee[leave.employee_id]
                if leave_unit == LeaveRequest.UNIT_HALF_DAY
                else paid_leave_days_by_employee[leave.employee_id]
            )
            d = overlap_start
            while d <= overlap_end:
                target_set.add(d)
                d += timedelta(days=1)

        rows = []
        for emp in employees:
            policy = policy_by_client.get(emp.client_id)
            monthly_working_days = Decimal(policy.monthly_working_days if policy else 24)
            standard_hours_per_day = Decimal(str(policy.standard_hours_per_day if policy else 8))
            policy_salary_basis = str(policy.salary_basis if policy else PayrollPolicy.BASIS_DAY)
            allow_extra_hours = bool(policy.allow_extra_hours_payout) if policy else False
            allow_extra_days = bool(policy.allow_extra_days_payout) if policy else False
            month_target_hours = monthly_working_days * standard_hours_per_day
            attendance_hours = hours_by_employee.get(emp.id, Decimal('0'))
            paid_leave_hours = paid_leave_hours_by_employee.get(emp.id, Decimal('0'))
            attendance_day_set = present_days_by_employee.get(emp.id, set())
            paid_leave_day_set = paid_leave_days_by_employee.get(emp.id, set())
            paid_leave_half_day_set = paid_leave_half_days_by_employee.get(emp.id, set())
            combined_paid_day_set = attendance_day_set.union(paid_leave_day_set)
            half_day_set = paid_leave_half_day_set - paid_leave_day_set
            half_day_count = Decimal(len(half_day_set)) * Decimal('0.5')
            paid_leave_days = Decimal(len(paid_leave_day_set)) + half_day_count
            present_days = Decimal(len(attendance_day_set))
            half_day_credit_set = half_day_set - combined_paid_day_set
            effective_present_days = Decimal(len(combined_paid_day_set)) + (Decimal(len(half_day_credit_set)) * Decimal('0.5'))
            paid_leave_day_hours = Decimal(len(paid_leave_day_set - attendance_day_set)) * standard_hours_per_day
            paid_leave_half_day_hours = half_day_count * standard_hours_per_day

            total_hours = attendance_hours + paid_leave_day_hours + paid_leave_half_day_hours + paid_leave_hours
            day_equivalent = (total_hours / standard_hours_per_day) if standard_hours_per_day > 0 else Decimal('0')

            payable_hours = total_hours if allow_extra_hours else min(total_hours, month_target_hours)
            payable_present_days = effective_present_days if allow_extra_days else min(effective_present_days, monthly_working_days)
            payable_days_from_hours = day_equivalent if allow_extra_days else min(day_equivalent, monthly_working_days)
            compensation = getattr(emp, 'compensation', None)
            compensation_basis = compensation.salary_basis if compensation else EmployeeCompensation.BASIS_MONTHLY
            monthly_salary = Decimal(str(compensation.monthly_salary or 0)) if compensation else Decimal('0')
            daily_salary = Decimal(str(compensation.daily_salary or 0)) if compensation else Decimal('0')
            hourly_salary = Decimal(str(compensation.hourly_salary or 0)) if compensation else Decimal('0')
            shift_name = str(getattr(getattr(compensation, 'shift', None), 'name', '') or '')

            if compensation_basis == EmployeeCompensation.BASIS_DAILY:
                per_day_rate = daily_salary
                per_hour_rate = (daily_salary / standard_hours_per_day) if standard_hours_per_day > 0 else Decimal('0')
                earned_salary_day_based = daily_salary * payable_present_days
                earned_salary_hour_based = hourly_salary * payable_hours if hourly_salary > 0 else per_hour_rate * payable_hours
                earned_salary = earned_salary_day_based
            elif compensation_basis == EmployeeCompensation.BASIS_HOURLY:
                per_hour_rate = hourly_salary
                per_day_rate = hourly_salary * standard_hours_per_day
                earned_salary_day_based = per_day_rate * payable_present_days
                earned_salary_hour_based = hourly_salary * payable_hours
                earned_salary = earned_salary_hour_based
            else:
                per_day_rate = (monthly_salary / monthly_working_days) if monthly_working_days > 0 else Decimal('0')
                per_hour_rate = (per_day_rate / standard_hours_per_day) if standard_hours_per_day > 0 else Decimal('0')
                earned_salary_day_based = per_day_rate * payable_present_days
                earned_salary_hour_based = per_hour_rate * payable_hours
                earned_salary = (
                    earned_salary_hour_based
                    if policy_salary_basis == PayrollPolicy.BASIS_HOUR
                    else earned_salary_day_based
                )

            rows.append({
                'employee_id': emp.id,
                'employee_name': f'{emp.first_name} {emp.last_name}'.strip(),
                'shift_name': shift_name,
                'client_id': emp.client_id,
                'month': f'{year:04d}-{month:02d}',
                'monthly_salary': float(round(monthly_salary, 2)),
                'daily_salary': float(round(daily_salary, 2)),
                'hourly_salary': float(round(hourly_salary, 2)),
                'policy_monthly_working_days': float(round(monthly_working_days, 2)),
                'policy_standard_hours_per_day': float(round(standard_hours_per_day, 2)),
                'salary_basis': compensation_basis,
                'policy_salary_basis': policy_salary_basis,
                'allow_extra_hours_payout': allow_extra_hours,
                'allow_extra_days_payout': allow_extra_days,
                'per_day_rate': float(round(per_day_rate, 2)),
                'per_hour_rate': float(round(per_hour_rate, 2)),
                'month_target_hours': float(round(month_target_hours, 2)),
                'present_days': float(round(present_days, 2)),
                'paid_leave_days': float(round(paid_leave_days, 2)),
                'paid_leave_hours': float(round(paid_leave_hours, 2)),
                'effective_present_days': float(round(effective_present_days, 2)),
                'worked_hours': float(round(total_hours, 2)),
                'worked_day_equivalent': float(round(day_equivalent, 2)),
                'payable_hours': float(round(payable_hours, 2)),
                'payable_present_days': float(round(payable_present_days, 2)),
                'payable_days_from_hours': float(round(payable_days_from_hours, 2)),
                'earned_salary_day_based': float(round(earned_salary_day_based, 2)),
                'earned_salary_hour_based': float(round(earned_salary_hour_based, 2)),
                'earned_salary': float(round(earned_salary, 2)),
            })

        return Response(rows, status=status.HTTP_200_OK)
