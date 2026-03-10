from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend

from .models import DynamicField, DynamicModel, DynamicRecord
from .serializers import DynamicFieldSerializer, DynamicModelSerializer, DynamicRecordSerializer


class TenantScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def _profile(self):
        try:
            return self.request.user.profile
        except Exception:
            return None

    def _is_superadmin(self):
        profile = self._profile()
        return self.request.user.is_superuser or (profile and profile.role == 'superadmin')


class DynamicModelViewSet(TenantScopedViewSet):
    serializer_class = DynamicModelSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'show_in_employee_form']
    search_fields = ['name', 'slug']
    ordering_fields = ['created_at', 'name']

    def get_queryset(self):
        if self._is_superadmin():
            return DynamicModel.objects.select_related('client')
        profile = self._profile()
        if not profile:
            return DynamicModel.objects.none()
        return DynamicModel.objects.select_related('client').filter(client=profile.client)

    def perform_create(self, serializer):
        if self._is_superadmin():
            serializer.save()
            return
        profile = self._profile()
        if not profile:
            raise PermissionDenied('User profile not found.')
        serializer.save(client=profile.client)

    def perform_update(self, serializer):
        if self._is_superadmin():
            serializer.save()
            return
        profile = self._profile()
        if not profile:
            raise PermissionDenied('User profile not found.')
        serializer.save(client=profile.client)

    @action(detail=False, methods=['post'], url_path='create-attendance')
    def create_attendance(self, request):
        """
        Create a pre-configured Attendance module using dynamic models/fields.
        """
        profile = self._profile()
        if self._is_superadmin():
            client_id = request.data.get('client')
            if not client_id:
                return Response({'client': 'This field is required for superadmin.'}, status=status.HTTP_400_BAD_REQUEST)
            from clients.models import Client
            try:
                client = Client.objects.get(id=client_id)
            except Client.DoesNotExist:
                return Response({'client': 'Client not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            if not profile or not profile.client:
                return Response({'detail': 'User is not assigned to any client.'}, status=status.HTTP_400_BAD_REQUEST)
            client = profile.client

        model_name = request.data.get('name') or 'Attendance'
        slug = request.data.get('slug') or 'attendance'

        dynamic_model, created = DynamicModel.objects.get_or_create(
            client=client,
            slug=slug,
            defaults={
                'name': model_name,
                'show_in_employee_form': False,
            },
        )
        defaults = [
            ('attendance_date', 'Attendance Date', 'date', True, True, []),
            ('status', 'Status', 'text', True, True, ['present', 'absent', 'leave', 'half-day']),
            ('shift', 'Shift', 'text', False, True, ['morning', 'evening', 'night']),
            ('check_in', 'Check In', 'text', False, True, []),
            ('check_out', 'Check Out', 'text', False, True, []),
            ('location_lat', 'Location Latitude', 'number', False, False, []),
            ('location_lng', 'Location Longitude', 'number', False, False, []),
            ('selfie_url', 'Selfie URL', 'text', False, False, []),
            ('remarks', 'Remarks', 'text', False, True, []),
        ]

        for order, (key, name, field_type, required, visible_to_users, choices) in enumerate(defaults, start=1):
            DynamicField.objects.get_or_create(
                dynamic_model=dynamic_model,
                key=key,
                defaults={
                    'name': name,
                    'field_type': field_type,
                    'required': required,
                    'visible_to_users': visible_to_users,
                    'choices_json': choices,
                    'sort_order': order,
                },
            )

        if not created:
            return Response(
                {'detail': f'Attendance model already exists for this client (slug={slug}). Fields verified.', 'id': dynamic_model.id},
                status=status.HTTP_200_OK,
            )

        return Response(
            {'detail': 'Attendance module created successfully.', 'id': dynamic_model.id},
            status=status.HTTP_201_CREATED,
        )


class DynamicFieldViewSet(TenantScopedViewSet):
    serializer_class = DynamicFieldSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['dynamic_model', 'field_type', 'required']
    search_fields = ['name', 'key']
    ordering_fields = ['sort_order', 'created_at']

    def get_queryset(self):
        if self._is_superadmin():
            return DynamicField.objects.select_related('dynamic_model', 'dynamic_model__client')
        profile = self._profile()
        if not profile:
            return DynamicField.objects.none()
        return DynamicField.objects.select_related('dynamic_model', 'dynamic_model__client').filter(
            dynamic_model__client=profile.client
        )

    def _validate_model_access(self, dynamic_model):
        if self._is_superadmin():
            return
        profile = self._profile()
        if not profile:
            raise PermissionDenied('User profile not found.')
        if dynamic_model.client_id != profile.client_id:
            raise PermissionDenied('Cannot access fields for another client.')

    def perform_create(self, serializer):
        dynamic_model = serializer.validated_data['dynamic_model']
        self._validate_model_access(dynamic_model)
        serializer.save()

    def perform_update(self, serializer):
        dynamic_model = serializer.validated_data.get('dynamic_model', serializer.instance.dynamic_model)
        self._validate_model_access(dynamic_model)
        serializer.save()


class DynamicRecordViewSet(TenantScopedViewSet):
    serializer_class = DynamicRecordSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['dynamic_model', 'employee']
    ordering_fields = ['created_at', 'updated_at']

    def get_queryset(self):
        if self._is_superadmin():
            return DynamicRecord.objects.select_related('dynamic_model', 'dynamic_model__client')
        profile = self._profile()
        if not profile:
            return DynamicRecord.objects.none()
        return DynamicRecord.objects.select_related('dynamic_model', 'dynamic_model__client').filter(
            dynamic_model__client=profile.client
        )

    def _validate_model_access(self, dynamic_model):
        if self._is_superadmin():
            return
        profile = self._profile()
        if not profile:
            raise PermissionDenied('User profile not found.')
        if dynamic_model.client_id != profile.client_id:
            raise PermissionDenied('Cannot access records for another client.')

    def perform_create(self, serializer):
        dynamic_model = serializer.validated_data['dynamic_model']
        self._validate_model_access(dynamic_model)
        serializer.save()

    def perform_update(self, serializer):
        dynamic_model = serializer.validated_data.get('dynamic_model', serializer.instance.dynamic_model)
        self._validate_model_access(dynamic_model)
        serializer.save()
