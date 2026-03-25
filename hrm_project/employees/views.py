from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from accounts.models import UserProfile
from core.mailers import send_branded_email
from .models import Employee
from .serializers import EmployeeSerializer
from rest_framework.permissions import IsAuthenticated


class EmployeeViewSet(viewsets.ModelViewSet):

    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def _build_unique_username(self, employee):
        if employee.employee_code:
            preferred = str(employee.employee_code).strip()
            if preferred and not User.objects.filter(username=preferred).exists():
                return preferred
        base = (employee.email.split('@')[0] if employee.email else '').strip().lower()
        if not base:
            base = f'employee{employee.id}'
        candidate = base
        i = 1
        while User.objects.filter(username=candidate).exists():
            candidate = f'{base}{i}'
            i += 1
        return candidate
    
    def _build_unique_email(self, employee):
        base = (employee.email.split('@')[0] if employee.email else '').strip().lower()
        domain = (employee.email.split('@')[1] if employee.email and '@' in employee.email else 'example.com').strip().lower()
        candidate = f'{base}@{domain}'
        i = 1
        while User.objects.filter(email__iexact=candidate).exists():
            candidate = f'{base}{i}@{domain}'
            i += 1
        return candidate

    def _ensure_login_user_for_employee(self, employee):
        role_permissions = list((employee.client_role.module_permissions if employee.client_role else []) or [])
        role_addons = list((employee.client_role.enabled_addons if employee.client_role else []) or [])
        existing_profile = (
            UserProfile.objects.select_related('user')
            .filter(client_id=employee.client_id, user__email__iexact=employee.email)
            .first()
        )
        if existing_profile:
            user = existing_profile.user
            user.first_name = employee.first_name
            user.last_name = employee.last_name
            user.email = employee.email
            user.save(update_fields=['first_name', 'last_name', 'email'])
            existing_profile.module_permissions = role_permissions
            existing_profile.enabled_addons = role_addons
            existing_profile.save(update_fields=['module_permissions', 'enabled_addons', 'updated_at'])
            return user

        username = self._build_unique_username(employee)
        email = self._build_unique_email(employee)
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=employee.first_name,
            last_name=employee.last_name,
            password=None,
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])

        UserProfile.objects.create(
            user=user,
            client_id=employee.client_id,
            role='employee',
            module_permissions=role_permissions,
            enabled_addons=role_addons,
        )
        return user

    def _send_password_setup_email(self, user, employee):
        if not user.email:
            return
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        app_prefix = str(getattr(settings, 'APP_URL_PREFIX', '') or '').rstrip('/')
        configured = list(getattr(settings, 'FRONTEND_BASE_URLS', []) or [])
        if configured:
            frontend_base = f"{str(configured[0]).rstrip('/')}{app_prefix}"
        else:
            frontend_base = self.request.build_absolute_uri(f'{app_prefix}/').rstrip('/')
        if not frontend_base:
            frontend_base = f"{str(getattr(settings, 'FRONTEND_BASE_URL', '') or '').strip().rstrip('/')}{app_prefix}"
        if not frontend_base:
            frontend_base = f'http://127.0.0.1:8000{app_prefix}'
        reset_link = f'{frontend_base}/reset-password/?uid={uid}&token={token}'

        send_branded_email(
            subject='Set your HRM account password',
            recipient_list=[user.email],
            heading='Set your HRM account password',
            greeting=f'Hi {user.first_name or user.username},',
            lines=[
                'Your employee account was created.',
                f'Employee ID: {employee.employee_code or employee.id}',
                'Use this Employee ID on the login page.',
                'Click below to set your password.',
            ],
            cta_text='Set Password',
            cta_url=reset_link,
            closing='If you did not expect this, please contact your HR admin.',
            client=employee.client,
            fail_silently=True,
        )
    
    def get_queryset(self):
        """Filter employees by user's client"""
        user = self.request.user
        role_filter = (self.request.query_params.get('role') or '').strip().lower()
        client_role_filter = (self.request.query_params.get('client_role') or '').strip()
        base_qs = Employee.objects.select_related('client', 'client_role', 'hr', 'manager')

        if user.is_superuser:
            qs = base_qs
            if role_filter in ('employee', 'hr', 'manager'):
                qs = qs.filter(role=role_filter)
            if client_role_filter.isdigit():
                qs = qs.filter(client_role_id=int(client_role_filter))
            return qs
        try:
            profile = user.profile
            # Super admin sees all, others see only their client's employees
            if profile.role == 'superadmin':
                qs = base_qs
            else:
                qs = base_qs.filter(client=profile.client)
            if role_filter in ('employee', 'hr', 'manager'):
                qs = qs.filter(role=role_filter)
            if client_role_filter.isdigit():
                qs = qs.filter(client_role_id=int(client_role_filter))
            return qs
        except:
            return Employee.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, 'profile', None)
        employee_client = serializer.validated_data.get('client')

        if not user.is_superuser:
            if not profile or not profile.client_id:
                raise PermissionDenied('User profile not found.')
            if profile.role != 'superadmin' and employee_client and employee_client.id != profile.client_id:
                raise PermissionDenied('You can only create employees for your own client.')

        with transaction.atomic():
            employee = serializer.save()
            login_user = self._ensure_login_user_for_employee(employee)
            self._send_password_setup_email(login_user, employee)

    def perform_update(self, serializer):
        with transaction.atomic():
            employee = serializer.save()
            self._ensure_login_user_for_employee(employee)
