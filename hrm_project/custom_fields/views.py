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
        if user.is_superuser:
            return CustomField.objects.all()
        try:
            profile = user.profile
            # Super admin sees all fields. Others can only work with employee fields.
            if profile.role == 'superadmin':
                return CustomField.objects.all()
            else:
                return CustomField.objects.filter(
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
        if user.is_superuser:
            return CustomFieldValue.objects.all()
        try:
            profile = user.profile
            # Super admin sees all, others see only their client's employee values
            if profile.role == 'superadmin':
                return CustomFieldValue.objects.all()
            else:
                from employees.models import Employee
                client_employees = Employee.objects.filter(client=profile.client)
                return CustomFieldValue.objects.filter(employee__in=client_employees)
        except:
            return CustomFieldValue.objects.none()
