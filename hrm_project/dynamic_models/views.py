from io import StringIO
import datetime

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import AttendanceBreak, DynamicField, DynamicModel, DynamicRecord
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
            # ('location_lat', 'Location Latitude', 'number', False, False, []),
            # ('location_lng', 'Location Longitude', 'number', False, False, []),
            # ('selfie_url', 'Selfie URL', 'text', False, False, []),
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
            return DynamicRecord.objects.select_related('dynamic_model', 'dynamic_model__client').prefetch_related('breaks')
        profile = self._profile()
        if not profile:
            return DynamicRecord.objects.none()
        return DynamicRecord.objects.select_related('dynamic_model', 'dynamic_model__client').prefetch_related('breaks').filter(
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
        record = serializer.save()
        if self._is_attendance_record(record):
            self._sync_break_models_from_data(record)
            self._sync_break_sessions_to_data(record)

    def perform_update(self, serializer):
        dynamic_model = serializer.validated_data.get('dynamic_model', serializer.instance.dynamic_model)
        self._validate_model_access(dynamic_model)
        record = serializer.save()
        if self._is_attendance_record(record):
            self._sync_break_models_from_data(record)
            self._sync_break_sessions_to_data(record)

    def _is_attendance_record(self, record):
        return bool(record and str(record.dynamic_model.slug or '').lower() == 'attendance')

    def _time_to_text(self, value):
        if isinstance(value, datetime.time):
            return value.strftime('%H:%M:%S')
        return str(value or '').strip()

    def _parse_break_time(self, value):
        raw = str(value or '').strip()
        if not raw:
            return None
        return datetime.time.fromisoformat(raw)

    def _sync_break_sessions_to_data(self, record):
        if not self._is_attendance_record(record):
            return
        sessions = []
        for item in record.breaks.order_by('break_in', 'id'):
            sessions.append({
                'break_in': self._time_to_text(item.break_in),
                'break_out': self._time_to_text(item.break_out),
            })
        data = dict(record.data or {})
        data['break_sessions'] = sessions
        record.data = data
        record.save(update_fields=['data', 'updated_at'])

    def _sync_break_models_from_data(self, record):
        if not self._is_attendance_record(record):
            return
        data = record.data or {}
        rows = data.get('break_sessions')
        if not isinstance(rows, list):
            return
        parsed_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            break_in = self._parse_break_time(row.get('break_in'))
            break_out = self._parse_break_time(row.get('break_out'))
            if not break_in:
                continue
            parsed_rows.append((break_in, break_out))
        with transaction.atomic():
            AttendanceBreak.objects.filter(attendance_record=record).delete()
            AttendanceBreak.objects.bulk_create([
                AttendanceBreak(attendance_record=record, break_in=break_in, break_out=break_out)
                for break_in, break_out in parsed_rows
            ])

    @action(detail=True, methods=['post'], url_path='break-in')
    def break_in(self, request, pk=None):
        record = self.get_object()
        if not self._is_attendance_record(record):
            return Response({'detail': 'Break In is supported only for attendance records.'}, status=status.HTTP_400_BAD_REQUEST)

        data = record.data or {}
        if not data.get('check_in'):
            return Response({'detail': 'Cannot break in before punch in.'}, status=status.HTTP_400_BAD_REQUEST)
        if data.get('check_out'):
            return Response({'detail': 'Cannot break in after punch out.'}, status=status.HTTP_400_BAD_REQUEST)
        if AttendanceBreak.objects.filter(attendance_record=record, break_out__isnull=True).exists():
            return Response({'detail': 'Previous break is still active. Please break out first.'}, status=status.HTTP_400_BAD_REQUEST)

        raw_at = request.data.get('at')
        try:
            at_time = self._parse_break_time(raw_at) if raw_at else timezone.localtime().time().replace(microsecond=0)
        except ValueError:
            return Response({'detail': 'Invalid time format for "at". Use HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)

        AttendanceBreak.objects.create(attendance_record=record, break_in=at_time)
        self._sync_break_sessions_to_data(record)
        refreshed = self.get_queryset().get(pk=record.pk)
        return Response(DynamicRecordSerializer(refreshed, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='break-out')
    def break_out(self, request, pk=None):
        record = self.get_object()
        if not self._is_attendance_record(record):
            return Response({'detail': 'Break Out is supported only for attendance records.'}, status=status.HTTP_400_BAD_REQUEST)

        data = record.data or {}
        if not data.get('check_in'):
            return Response({'detail': 'Cannot break out before punch in.'}, status=status.HTTP_400_BAD_REQUEST)
        if data.get('check_out'):
            return Response({'detail': 'Cannot break out after punch out.'}, status=status.HTTP_400_BAD_REQUEST)

        open_break = (
            AttendanceBreak.objects
            .filter(attendance_record=record, break_out__isnull=True)
            .order_by('-break_in', '-id')
            .first()
        )
        if not open_break:
            return Response({'detail': 'No active break found. Please break in first.'}, status=status.HTTP_400_BAD_REQUEST)

        raw_at = request.data.get('at')
        try:
            at_time = self._parse_break_time(raw_at) if raw_at else timezone.localtime().time().replace(microsecond=0)
        except ValueError:
            return Response({'detail': 'Invalid time format for "at". Use HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)

        open_break.break_out = at_time
        open_break.save(update_fields=['break_out', 'updated_at'])
        self._sync_break_sessions_to_data(record)
        refreshed = self.get_queryset().get(pk=record.pk)
        return Response(DynamicRecordSerializer(refreshed, context={'request': request}).data, status=status.HTTP_200_OK)


class AutoClockoutRunView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def _run(self, dry_run=False, no_email=False):
        dry_run = bool(dry_run)
        no_email = bool(no_email)

        out = StringIO()
        try:
            call_command(
                'auto_clockout_attendance',
                dry_run=dry_run,
                no_email=no_email,
                stdout=out,
            )
        except Exception as exc:
            return Response(
                {
                    'detail': 'Failed to run auto clock-out command.',
                    'error': str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        output = out.getvalue().strip()
        lines = [line for line in output.splitlines() if line.strip()]
        return Response(
            {
                'detail': 'Auto clock-out command executed.',
                'dry_run': dry_run,
                'no_email': no_email,
                'output': output,
                'lines': lines,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        dry_run = str(request.data.get('dry_run', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        no_email = str(request.data.get('no_email', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        return self._run(dry_run=dry_run, no_email=no_email)

    def get(self, request):
        dry_run = str(request.query_params.get('dry_run', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        no_email = str(request.query_params.get('no_email', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        return self._run(dry_run=dry_run, no_email=no_email)
