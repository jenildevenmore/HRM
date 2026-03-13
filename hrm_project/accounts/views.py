from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
import re
from .models import UserProfile, ClientPermissionGroup
from .serializers import UserProfileSerializer, UserSerializer, ClientPermissionGroupSerializer
from dynamic_models.models import DynamicModel
from core.mailers import send_branded_email


def _frontend_base_url(request):
    configured = list(getattr(settings, 'FRONTEND_BASE_URLS', []) or [])
    if configured:
        return str(configured[0]).rstrip('/')
    single = str(getattr(settings, 'FRONTEND_BASE_URL', '') or '').strip().rstrip('/')
    if single:
        return single
    built = request.build_absolute_uri('/').rstrip('/')
    if built:
        return built
    return 'http://127.0.0.1:8000'


class UserProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user profiles with multi-tenant support
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def _is_superadmin(self, user):
        if user.is_superuser:
            return True
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'superadmin')

    def _is_client_admin(self, user):
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'admin')
    
    def get_queryset(self):
        """Filter by authenticated user's client"""
        user = self.request.user
        base_qs = UserProfile.objects.select_related('user', 'client', 'permission_group')
        if user.is_superuser:
            return base_qs
        try:
            profile = user.profile
            # Super admin can see all, others see only their client
            if profile.role == 'superadmin':
                return base_qs
            else:
                return base_qs.filter(client=profile.client)
        except UserProfile.DoesNotExist:
            return UserProfile.objects.none()

    def perform_update(self, serializer):
        actor = self.request.user
        actor_profile = getattr(actor, 'profile', None)
        target = serializer.instance

        if self._is_superadmin(actor):
            serializer.save()
            return

        if not self._is_client_admin(actor):
            raise PermissionDenied('Only client admin can update user permissions.')

        if not actor_profile or actor_profile.client_id != target.client_id:
            raise PermissionDenied('You cannot update users from another client.')

        serializer.save()
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user profile"""
        if request.user.is_superuser:
            return Response({
                'id': None,
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'email': request.user.email,
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                },
                'client': None,
                'role': 'superadmin',
                'role_display': 'Super Admin',
                'created_at': None,
            })
        try:
            profile = request.user.profile
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'User profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """Register a new user (for super admin only via API)"""
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        client_id = request.data.get('client_id')
        role = request.data.get('role', 'employee')
        
        if not all([username, email, password, client_id]):
            return Response(
                {'error': 'Missing required fields'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if User.objects.filter(username=username).exists():
            return Response(
                {'error': 'Username already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            
            from clients.models import Client
            client = Client.objects.get(id=client_id)
            
            profile = UserProfile.objects.create(
                user=user,
                client=client,
                role=role
            )

            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_base = _frontend_base_url(request)
            reset_link = f'{frontend_base}/reset-password/?uid={uid}&token={token}'

            email_sent = False
            email_error = ''
            if email:
                try:
                    send_branded_email(
                        subject='Set your HRM account password',
                        recipient_list=[email],
                        heading='Set your HRM account password',
                        greeting=f'Hello {username},',
                        lines=[
                            'Your HRM account has been created.',
                            'Use the button below to set/reset your password.',
                        ],
                        cta_text='Set Password',
                        cta_url=reset_link,
                        closing='If you did not request this, contact your administrator.',
                        client=client,
                        fail_silently=False,
                    )
                    email_sent = True
                except Exception as mail_exc:
                    email_error = str(mail_exc)

            serializer = self.get_serializer(profile)
            response_data = serializer.data
            response_data['password_setup_link'] = reset_link
            response_data['password_reset_email_sent'] = email_sent
            if email_error:
                response_data['password_reset_email_error'] = email_error
            return Response(response_data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny], url_path='password-setup-confirm')
    def password_setup_confirm(self, request):
        uid = str(request.data.get('uid') or '').strip()
        token = str(request.data.get('token') or '').strip()
        new_password = str(request.data.get('new_password') or '')

        if not uid or not token or not new_password:
            return Response(
                {'detail': 'uid, token and new_password are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=user_id)
        except Exception:
            return Response({'detail': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({'detail': 'Reset link is invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({'new_password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'detail': 'Password set successfully.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny], url_path='password-reset-request')
    def password_reset_request(self, request):
        identifier = str(
            request.data.get('identifier')
            or request.data.get('email')
            or request.data.get('username')
            or ''
        ).strip()
        client_id_raw = str(request.data.get('client_id') or '').strip()

        if not identifier:
            return Response(
                {'detail': 'Email or username is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile_qs = UserProfile.objects.select_related('user', 'client').filter(user__is_active=True)
        if client_id_raw:
            try:
                profile_qs = profile_qs.filter(client_id=int(client_id_raw))
            except (TypeError, ValueError):
                return Response({'client_id': 'Invalid client id.'}, status=status.HTTP_400_BAD_REQUEST)

        profile = profile_qs.filter(
            Q(user__email__iexact=identifier) | Q(user__username__iexact=identifier)
        ).order_by('id').first()

        # Do not reveal whether an account exists.
        if not profile:
            return Response(
                {'detail': 'If an account exists for this user, a reset link has been sent.'},
                status=status.HTTP_200_OK,
            )

        user = profile.user
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        frontend_base = _frontend_base_url(request)
        reset_link = f'{frontend_base}/reset-password/?uid={uid}&token={token}'

        email_sent = False
        email_error = ''
        if user.email:
            try:
                send_branded_email(
                    subject='Reset your HRM account password',
                    recipient_list=[user.email],
                    heading='Password reset request',
                    greeting=f'Hello {user.username},',
                    lines=[
                        'We received a request to reset your HRM password.',
                        'Use the button below to reset your password.',
                    ],
                    cta_text='Reset Password',
                    cta_url=reset_link,
                    closing='If you did not request this, you can ignore this email.',
                    client=profile.client,
                    fail_silently=False,
                )
                email_sent = True
            except Exception as exc:
                email_error = str(exc)

        payload = {'detail': 'If an account exists for this user, a reset link has been sent.'}
        if settings.DEBUG:
            payload['debug_reset_link'] = reset_link
            payload['email_sent'] = email_sent
            if email_error:
                payload['email_error'] = email_error
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='permission-options')
    def permission_options(self, request):
        if not (self._is_superadmin(request.user) or self._is_client_admin(request.user)):
            return Response({'detail': 'Only client admin can view permission options.'}, status=status.HTTP_403_FORBIDDEN)

        profile = getattr(request.user, 'profile', None)
        if self._is_superadmin(request.user):
            client_id = request.query_params.get('client')
            if not client_id:
                return Response({'client': 'This field is required for superadmin.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            client_id = profile.client_id if profile else None

        dynamic_models = DynamicModel.objects.filter(client_id=client_id).order_by('name')

        static_groups = [
            {
                'title': 'Employees',
                'permissions': [
                    {'key': 'employees.view', 'label': 'Can view Employees'},
                    {'key': 'employees.create', 'label': 'Can create Employees'},
                    {'key': 'employees.edit', 'label': 'Can edit Employees'},
                    {'key': 'employees.delete', 'label': 'Can delete Employees'},
                ],
            },
            {
                'title': 'Attendance',
                'permissions': [
                    {'key': 'attendance.view', 'label': 'Can view Attendance'},
                    {'key': 'attendance.create', 'label': 'Can create Attendance'},
                    {'key': 'attendance.edit', 'label': 'Can edit Attendance'},
                    {'key': 'attendance.delete', 'label': 'Can delete Attendance'},
                ],
            },
            {
                'title': 'Leave Management',
                'permissions': [
                    {'key': 'leaves.view', 'label': 'Can view Leaves'},
                    {'key': 'leaves.create', 'label': 'Can create Leaves'},
                    {'key': 'leaves.edit', 'label': 'Can edit Leaves'},
                    {'key': 'leaves.delete', 'label': 'Can delete Leaves'},
                    {'key': 'leaves.approve', 'label': 'Can approve/reject Leaves'},
                ],
            },
            {
                'title': 'Holidays',
                'permissions': [
                    {'key': 'holidays.view', 'label': 'Can view Holidays'},
                    {'key': 'holidays.create', 'label': 'Can create Holidays'},
                    {'key': 'holidays.edit', 'label': 'Can edit Holidays'},
                    {'key': 'holidays.delete', 'label': 'Can delete Holidays'},
                ],
            },
            {
                'title': 'Shifts',
                'permissions': [
                    {'key': 'shifts.view', 'label': 'Can view Shifts'},
                    {'key': 'shifts.create', 'label': 'Can create Shifts'},
                    {'key': 'shifts.edit', 'label': 'Can edit Shifts'},
                    {'key': 'shifts.delete', 'label': 'Can delete Shifts'},
                ],
            },
            {
                'title': 'Bank',
                'permissions': [
                    {'key': 'bank.view', 'label': 'Can view Bank'},
                    {'key': 'bank.create', 'label': 'Can create Bank'},
                    {'key': 'bank.edit', 'label': 'Can edit Bank'},
                    {'key': 'bank.delete', 'label': 'Can delete Bank'},
                ],
            },
            {
                'title': 'Policy',
                'permissions': [
                    {'key': 'policy.view', 'label': 'Can view Policy'},
                    {'key': 'policy.create', 'label': 'Can create Policy'},
                    {'key': 'policy.edit', 'label': 'Can edit Policy'},
                    {'key': 'policy.delete', 'label': 'Can delete Policy'},
                ],
            },
            {
                'title': 'Documents',
                'permissions': [
                    {'key': 'documents.view', 'label': 'Can view Documents'},
                    {'key': 'documents.create', 'label': 'Can create Documents'},
                    {'key': 'documents.edit', 'label': 'Can edit Documents'},
                    {'key': 'documents.delete', 'label': 'Can delete Documents'},
                ],
            },
            {
                'title': 'Import / Export',
                'permissions': [
                    {'key': 'import_export.view', 'label': 'Can view Import / Export'},
                    {'key': 'import_export.import', 'label': 'Can import records'},
                    {'key': 'import_export.export', 'label': 'Can export records'},
                ],
            },
            {
                'title': 'Custom Fields',
                'permissions': [
                    {'key': 'custom_fields.view', 'label': 'Can view Custom Fields'},
                    {'key': 'custom_fields.create', 'label': 'Can create Custom Fields'},
                    {'key': 'custom_fields.edit', 'label': 'Can edit Custom Fields'},
                    {'key': 'custom_fields.delete', 'label': 'Can delete Custom Fields'},
                ],
            },
            {
                'title': 'Dynamic Model Setup',
                'permissions': [
                    {'key': 'dynamic_models.view', 'label': 'Can view Dynamic Models'},
                    {'key': 'dynamic_models.create', 'label': 'Can create Dynamic Models'},
                    {'key': 'dynamic_models.edit', 'label': 'Can edit Dynamic Models'},
                    {'key': 'dynamic_models.delete', 'label': 'Can delete Dynamic Models'},
                ],
            },
            {
                'title': 'Activity Logs',
                'permissions': [
                    {'key': 'activity_logs.view', 'label': 'Can view Activity Logs'},
                ],
            },
        ]

        dynamic_groups = []
        for model in dynamic_models:
            if str(model.slug).lower() == 'attendance':
                continue
            dynamic_groups.append({
                'title': model.name,
                'permissions': [
                    {'key': f'dynamic_model.{model.id}.view', 'label': f'Can view {model.name}'},
                    {'key': f'dynamic_model.{model.id}.create', 'label': f'Can create {model.name}'},
                    {'key': f'dynamic_model.{model.id}.edit', 'label': f'Can edit {model.name}'},
                    {'key': f'dynamic_model.{model.id}.delete', 'label': f'Can delete {model.name}'},
                ],
            })

        return Response(static_groups + dynamic_groups)

    @action(detail=True, methods=['post'], url_path='set-permissions')
    def set_permissions(self, request, pk=None):
        actor = request.user
        target = self.get_object()

        if self._is_superadmin(actor):
            pass
        elif self._is_client_admin(actor):
            actor_profile = getattr(actor, 'profile', None)
            if not actor_profile or actor_profile.client_id != target.client_id:
                return Response({'detail': 'You cannot update users from another client.'}, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response({'detail': 'Only client admin can update permissions.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(target, data={
            'module_permissions': request.data.get('module_permissions', []),
            'enabled_addons': request.data.get('enabled_addons', []),
        }, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='assign-group')
    def assign_group(self, request, pk=None):
        actor = request.user
        target = self.get_object()

        if not (self._is_superadmin(actor) or self._is_client_admin(actor)):
            return Response({'detail': 'Only client admin can assign groups.'}, status=status.HTTP_403_FORBIDDEN)

        actor_profile = getattr(actor, 'profile', None)
        if self._is_client_admin(actor) and (not actor_profile or actor_profile.client_id != target.client_id):
            return Response({'detail': 'You cannot update users from another client.'}, status=status.HTTP_403_FORBIDDEN)

        group_id = request.data.get('permission_group')
        if not group_id:
            target.permission_group = None
            target.save(update_fields=['permission_group', 'updated_at'])
            return Response(self.get_serializer(target).data)

        try:
            group = ClientPermissionGroup.objects.get(id=group_id)
        except ClientPermissionGroup.DoesNotExist:
            return Response({'permission_group': 'Group not found.'}, status=status.HTTP_404_NOT_FOUND)

        if target.client_id != group.client_id:
            return Response({'permission_group': 'Group must belong to the same client.'}, status=status.HTTP_400_BAD_REQUEST)

        target.permission_group = group
        target.save(update_fields=['permission_group', 'updated_at'])
        return Response(self.get_serializer(target).data)


class ClientPermissionGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ClientPermissionGroupSerializer
    permission_classes = [IsAuthenticated]

    def _is_superadmin(self, user):
        if user.is_superuser:
            return True
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'superadmin')

    def _is_client_admin(self, user):
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'admin')

    def get_queryset(self):
        user = self.request.user
        qs = ClientPermissionGroup.objects.select_related('client').annotate(user_count=Count('users'))
        if self._is_superadmin(user):
            return qs
        profile = getattr(user, 'profile', None)
        if profile and profile.client_id:
            return qs.filter(client_id=profile.client_id)
        return ClientPermissionGroup.objects.none()

    def _validate_dynamic_model_permissions(self, client_id, permissions):
        dynamic_ids = []
        for key in permissions or []:
            match = re.fullmatch(r'dynamic_model\.(\d+)\.(view|create|edit|delete)', str(key))
            if match:
                dynamic_ids.append(int(match.group(1)))
        if not dynamic_ids:
            return
        valid_ids = set(
            DynamicModel.objects.filter(client_id=client_id, id__in=dynamic_ids).values_list('id', flat=True)
        )
        invalid = sorted(set(dynamic_ids) - valid_ids)
        if invalid:
            raise PermissionDenied(f'Invalid dynamic model permissions for this client: {invalid}')

    def create(self, request, *args, **kwargs):
        user = request.user
        payload = request.data.copy()

        if self._is_superadmin(user):
            if not payload.get('client'):
                return Response({'client': 'This field is required for superadmin.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            profile = getattr(user, 'profile', None)
            if not self._is_client_admin(user) or not profile or not profile.client_id:
                return Response({'detail': 'Only client admin can create groups.'}, status=status.HTTP_403_FORBIDDEN)
            payload['client'] = profile.client_id

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        user = self.request.user
        if self._is_superadmin(user):
            client = serializer.validated_data.get('client')
            self._validate_dynamic_model_permissions(client.id if client else None, serializer.validated_data.get('module_permissions', []))
            serializer.save()
            return

        profile = getattr(user, 'profile', None)
        if not self._is_client_admin(user) or not profile or not profile.client_id:
            raise PermissionDenied('Only client admin can create groups.')

        self._validate_dynamic_model_permissions(profile.client_id, serializer.validated_data.get('module_permissions', []))
        serializer.save(client=profile.client)

    def perform_update(self, serializer):
        user = self.request.user
        group = serializer.instance
        if self._is_superadmin(user):
            client = serializer.validated_data.get('client', group.client)
            self._validate_dynamic_model_permissions(client.id if client else None, serializer.validated_data.get('module_permissions', group.module_permissions))
            serializer.save()
            return

        profile = getattr(user, 'profile', None)
        if not self._is_client_admin(user) or not profile or profile.client_id != group.client_id:
            raise PermissionDenied('Only client admin can update groups for this client.')

        self._validate_dynamic_model_permissions(profile.client_id, serializer.validated_data.get('module_permissions', group.module_permissions))
        serializer.save(client=profile.client)

    def perform_destroy(self, instance):
        user = self.request.user
        if self._is_superadmin(user):
            instance.delete()
            return

        profile = getattr(user, 'profile', None)
        if not self._is_client_admin(user) or not profile or profile.client_id != instance.client_id:
            raise PermissionDenied('Only client admin can delete groups for this client.')

        UserProfile.objects.filter(permission_group=instance).update(permission_group=None)
        instance.delete()

