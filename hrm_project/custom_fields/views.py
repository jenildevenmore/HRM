from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import CustomField, CustomFieldValue
from .serializers import CustomFieldSerializer, CustomFieldValueSerializer
from rest_framework.permissions import IsAuthenticated


class CustomFieldViewSet(viewsets.ModelViewSet):

    serializer_class = CustomFieldSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['model_name', 'client']
    search_fields = ['field_name', 'model_name']
    
    def get_queryset(self):
        """Filter custom fields by user's client"""
        user = self.request.user
        base_qs = CustomField.objects.select_related('client')
        if user.is_superuser:
            return base_qs
        try:
            profile = user.profile
            # Super admin sees all fields. Others can only work with employee fields.
            if profile.role == 'superadmin':
                return base_qs
            else:
                return base_qs.filter(
                    client=profile.client,
                    model_name='Employee',
                )
        except:
            return CustomField.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser:
            serializer.save()
            return
        profile = user.profile
        if profile.role != 'superadmin' and serializer.validated_data.get('model_name') == 'Client':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only superadmin can create Client custom fields.')
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        if user.is_superuser:
            serializer.save()
            return
        profile = user.profile
        if profile.role != 'superadmin' and serializer.validated_data.get('model_name') == 'Client':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only superadmin can update Client custom fields.')
        serializer.save()


class CustomFieldValueViewSet(viewsets.ModelViewSet):

    serializer_class = CustomFieldValueSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['employee', 'field']
    
    def get_queryset(self):
        """Filter custom field values by user's client"""
        user = self.request.user
        base_qs = CustomFieldValue.objects.select_related('employee', 'employee__client', 'field', 'field__client')
        if user.is_superuser:
            return base_qs
        try:
            profile = user.profile
            # Super admin sees all, others see only their client's employee values
            if profile.role == 'superadmin':
                return base_qs
            else:
                return base_qs.filter(employee__client=profile.client)
        except:
            return CustomFieldValue.objects.none()
