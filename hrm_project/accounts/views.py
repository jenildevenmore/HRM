from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.utils.http import urlsafe_base64_decode
import re
from .models import UserProfile, ClientPermissionGroup
from .serializers import UserProfileSerializer, UserSerializer, ClientPermissionGroupSerializer
from dynamic_models.models import DynamicModel


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
        if user.is_superuser:
            return UserProfile.objects.all()
        try:
            profile = user.profile
            # Super admin can see all, others see only their client
            if profile.role == 'superadmin':
                return UserProfile.objects.all()
            else:
                return UserProfile.objects.filter(client=profile.client)
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
            
            serializer = self.get_serializer(profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
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
        qs = ClientPermissionGroup.objects.annotate(user_count=Count('users'))
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

