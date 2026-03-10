from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import Client, ClientRole
from .serializers import ClientSerializer, ClientRoleSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def _is_superadmin(self):
        user = self.request.user
        if user.is_superuser:
            return True
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'superadmin')

    def _is_client_admin(self):
        profile = getattr(self.request.user, 'profile', None)
        return bool(profile and profile.role == 'admin')
    
    def get_queryset(self):
        """Filter clients by user role"""
        user = self.request.user
        base_qs = Client.objects.all()
        if user.is_superuser:
            return base_qs
        try:
            profile = user.profile
            # Super admin sees all clients, others see only their own client
            if profile.role == 'superadmin':
                return base_qs
            elif profile.client:
                return base_qs.filter(id=profile.client.id)
            else:
                return Client.objects.none()
        except:
            return Client.objects.none()

    def create(self, request, *args, **kwargs):
        if not self._is_superadmin():
            return Response({'detail': 'Only superadmin can create clients.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not self._is_superadmin():
            return Response({'detail': 'Only superadmin can update clients.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not self._is_superadmin():
            return Response({'detail': 'Only superadmin can update clients.'}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._is_superadmin():
            return Response({'detail': 'Only superadmin can delete clients.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='public')
    def public(self, request):
        """Public client list for client-first login screen."""
        clients = Client.objects.order_by('name').values('id', 'name', 'domain')
        return Response(list(clients))

    @action(detail=False, methods=['get', 'post'], url_path='settings')
    def app_settings(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)

        if self._is_superadmin():
            client_id = request.query_params.get('client_id') or request.data.get('client_id')
            if not client_id:
                return Response({'client_id': 'This field is required for superadmin.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                client = Client.objects.get(id=client_id)
            except Client.DoesNotExist:
                return Response({'detail': 'Client not found.'}, status=status.HTTP_404_NOT_FOUND)
        elif self._is_client_admin() and profile and profile.client_id:
            client = profile.client
        else:
            return Response({'detail': 'Only superadmin or client admin can manage settings.'}, status=status.HTTP_403_FORBIDDEN)

        if request.method.lower() == 'get':
            return Response(client.app_settings or {}, status=status.HTTP_200_OK)

        incoming_settings = request.data.get('app_settings', {})
        if incoming_settings is None:
            incoming_settings = {}
        if not isinstance(incoming_settings, dict):
            return Response({'app_settings': 'app_settings must be an object.'}, status=status.HTTP_400_BAD_REQUEST)

        client.app_settings = incoming_settings
        client.save(update_fields=['app_settings'])
        return Response(client.app_settings, status=status.HTTP_200_OK)


class ClientRoleViewSet(viewsets.ModelViewSet):
    serializer_class = ClientRoleSerializer
    permission_classes = [IsAuthenticated]

    def _is_superadmin(self):
        user = self.request.user
        if user.is_superuser:
            return True
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.role == 'superadmin')

    def _is_client_admin(self):
        profile = getattr(self.request.user, 'profile', None)
        return bool(profile and profile.role == 'admin')

    def get_queryset(self):
        user = self.request.user
        base_qs = ClientRole.objects.select_related('client').all()

        client_id = self.request.query_params.get('client')
        base_role = (self.request.query_params.get('base_role') or '').strip().lower()
        active = self.request.query_params.get('active')

        if user.is_superuser:
            qs = base_qs
        else:
            profile = getattr(user, 'profile', None)
            if not profile:
                return ClientRole.objects.none()
            if profile.role == 'superadmin':
                qs = base_qs
            elif profile.client_id:
                qs = base_qs.filter(client_id=profile.client_id)
            else:
                return ClientRole.objects.none()

        if client_id:
            qs = qs.filter(client_id=client_id)
        if base_role in ('employee', 'hr', 'manager'):
            qs = qs.filter(base_role=base_role)
        if active in ('true', '1'):
            qs = qs.filter(is_active=True)
        elif active in ('false', '0'):
            qs = qs.filter(is_active=False)
        return qs

    def create(self, request, *args, **kwargs):
        if not (self._is_superadmin() or self._is_client_admin()):
            return Response({'detail': 'Only superadmin or client admin can create roles.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not (self._is_superadmin() or self._is_client_admin()):
            return Response({'detail': 'Only superadmin or client admin can update roles.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not (self._is_superadmin() or self._is_client_admin()):
            return Response({'detail': 'Only superadmin or client admin can update roles.'}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not (self._is_superadmin() or self._is_client_admin()):
            return Response({'detail': 'Only superadmin or client admin can delete roles.'}, status=status.HTTP_403_FORBIDDEN)
        role_obj = self.get_object()
        if role_obj.employees.exists():
            return Response(
                {'detail': 'Cannot delete role assigned to employees. Reassign employees first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

