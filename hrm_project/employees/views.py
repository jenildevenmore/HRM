from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from accounts.models import UserProfile
from .models import Employee
from .serializers import EmployeeSerializer
from rest_framework.permissions import IsAuthenticated


class EmployeeViewSet(viewsets.ModelViewSet):

    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def _build_unique_username(self, employee):
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
        )
        return user

    def _send_password_setup_email(self, user):
        if not user.email:
            return
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        base_urls = getattr(settings, 'FRONTEND_BASE_URLS', None) or [
            getattr(settings, 'FRONTEND_BASE_URL', 'http://127.0.0.1:8001')
        ]
        reset_links = [
            f"{str(base_url).rstrip('/')}/reset-password/?uid={uid}&token={token}"
            for base_url in base_urls
            if str(base_url).strip()
        ]
        if not reset_links:
            reset_links = [f'http://127.0.0.1:8001/reset-password/?uid={uid}&token={token}']
        links_text = '\n'.join(reset_links)

        subject = 'Set your HRM account password'
        message = (
            f'Hi {user.first_name or user.username},\n\n'
            'Your employee account was created.\n'
            f'Username: {user.username}\n\n'
            'Please set your password using one of these links:\n'
            f'{links_text}\n\n'
            'If you did not expect this, please contact your HR admin.'
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hrm.local'),
            recipient_list=[user.email],
            fail_silently=True,
        )
    
    def get_queryset(self):
        """Filter employees by user's client"""
        user = self.request.user
        role_filter = (self.request.query_params.get('role') or '').strip().lower()

        if user.is_superuser:
            qs = Employee.objects.all()
            return qs.filter(role=role_filter) if role_filter in ('employee', 'hr', 'manager') else qs
        try:
            profile = user.profile
            # Super admin sees all, others see only their client's employees
            if profile.role == 'superadmin':
                qs = Employee.objects.all()
            else:
                qs = Employee.objects.filter(client=profile.client)
            if role_filter in ('employee', 'hr', 'manager'):
                qs = qs.filter(role=role_filter)
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
            self._send_password_setup_email(login_user)
