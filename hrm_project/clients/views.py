from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import Client
from .serializers import ClientSerializer
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
    
    def get_queryset(self):
        """Filter clients by user role"""
        user = self.request.user
        if user.is_superuser:
            return Client.objects.all()
        try:
            profile = user.profile
            # Super admin sees all clients, others see only their own client
            if profile.role == 'superadmin':
                return Client.objects.all()
            elif profile.client:
                return Client.objects.filter(id=profile.client.id)
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

