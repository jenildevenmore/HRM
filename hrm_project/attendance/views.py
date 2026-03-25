import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AttendanceBreak, AttendanceRecord
from .serializers import AttendanceBreakSerializer, AttendanceRecordSerializer


class _AttendanceAccessMixin:
    def _profile(self):
        try:
            return self.request.user.profile
        except Exception:
            return None

    def _is_superadmin(self):
        profile = self._profile()
        return self.request.user.is_superuser or bool(profile and profile.role == 'superadmin')

    def _is_client_admin(self):
        profile = self._profile()
        return bool(profile and profile.role == 'admin')

    def _client_id_from_auth(self):
        auth = getattr(self.request, 'auth', None)
        try:
            return auth.get('client_id') if auth is not None else None
        except Exception:
            return None

    def _client_id(self):
        profile = self._profile()
        if profile and profile.client_id:
            return profile.client_id
        return self._client_id_from_auth()

    def _can_manage(self):
        return self._is_superadmin() or self._is_client_admin()


class AttendanceRecordViewSet(_AttendanceAccessMixin, viewsets.ModelViewSet):
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['employee', 'attendance_date', 'status', 'shift']
    ordering_fields = ['attendance_date', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = AttendanceRecord.objects.select_related('client', 'employee', 'shift').prefetch_related('breaks')
        if self._is_superadmin():
            client = self.request.query_params.get('client')
            if client:
                return qs.filter(client_id=client)
            return qs
        client_id = self._client_id()
        if not client_id:
            return AttendanceRecord.objects.none()
        return qs.filter(client_id=client_id)

    def perform_create(self, serializer):
        if not self._can_manage():
            raise PermissionDenied('Only superadmin/client admin can manage attendance.')
        if self._is_superadmin():
            client = serializer.validated_data.get('client')
            if not client:
                raise PermissionDenied('client is required for superadmin.')
            serializer.save(client=client)
            return
        client_id = self._client_id()
        if not client_id:
            raise PermissionDenied('Client not resolved from login.')
        serializer.save(client_id=client_id)

    def perform_update(self, serializer):
        if not self._can_manage():
            raise PermissionDenied('Only superadmin/client admin can manage attendance.')
        instance = serializer.instance
        if not self._is_superadmin() and instance.client_id != self._client_id():
            raise PermissionDenied('Not allowed for this client.')
        serializer.save(client_id=instance.client_id)

    def perform_destroy(self, instance):
        if not self._can_manage():
            raise PermissionDenied('Only superadmin/client admin can manage attendance.')
        if not self._is_superadmin() and instance.client_id != self._client_id():
            raise PermissionDenied('Not allowed for this client.')
        instance.delete()

    def _parse_time(self, raw):
        text = str(raw or '').strip()
        if not text:
            return None
        return datetime.time.fromisoformat(text)

    @action(detail=True, methods=['post'], url_path='break-in')
    def break_in(self, request, pk=None):
        record = self.get_object()
        if not record.check_in:
            return Response({'detail': 'Cannot break in before punch in.'}, status=status.HTTP_400_BAD_REQUEST)
        if record.check_out:
            return Response({'detail': 'Cannot break in after punch out.'}, status=status.HTTP_400_BAD_REQUEST)
        if record.breaks.filter(break_out__isnull=True).exists():
            return Response({'detail': 'Previous break is still open.'}, status=status.HTTP_400_BAD_REQUEST)
        raw_at = request.data.get('at')
        try:
            at_time = self._parse_time(raw_at) if raw_at else timezone.localtime().time().replace(microsecond=0)
        except ValueError:
            return Response({'detail': 'Invalid time format. Use HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)
        AttendanceBreak.objects.create(attendance=record, break_in=at_time)
        refreshed = self.get_queryset().get(pk=record.pk)
        return Response(AttendanceRecordSerializer(refreshed, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='break-out')
    def break_out(self, request, pk=None):
        record = self.get_object()
        if not record.check_in:
            return Response({'detail': 'Cannot break out before punch in.'}, status=status.HTTP_400_BAD_REQUEST)
        if record.check_out:
            return Response({'detail': 'Cannot break out after punch out.'}, status=status.HTTP_400_BAD_REQUEST)
        open_break = record.breaks.filter(break_out__isnull=True).order_by('-break_in', '-id').first()
        if not open_break:
            return Response({'detail': 'No active break found.'}, status=status.HTTP_400_BAD_REQUEST)
        raw_at = request.data.get('at')
        try:
            at_time = self._parse_time(raw_at) if raw_at else timezone.localtime().time().replace(microsecond=0)
        except ValueError:
            return Response({'detail': 'Invalid time format. Use HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)
        open_break.break_out = at_time
        open_break.save(update_fields=['break_out', 'updated_at'])
        refreshed = self.get_queryset().get(pk=record.pk)
        return Response(AttendanceRecordSerializer(refreshed, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='punch-out')
    def punch_out(self, request, pk=None):
        record = self.get_object()
        if not record.check_in:
            return Response({'detail': 'Cannot punch out before punch in.'}, status=status.HTTP_400_BAD_REQUEST)
        if record.check_out:
            return Response({'detail': 'Already punched out.'}, status=status.HTTP_400_BAD_REQUEST)
        if record.breaks.filter(break_out__isnull=True).exists():
            return Response({'detail': 'Close active break before punch out.'}, status=status.HTTP_400_BAD_REQUEST)
        raw_at = request.data.get('at')
        try:
            at_time = self._parse_time(raw_at) if raw_at else timezone.localtime().time().replace(microsecond=0)
        except ValueError:
            return Response({'detail': 'Invalid time format. Use HH:MM:SS.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            record.check_out = at_time
            record.save(update_fields=['check_out', 'updated_at'])
        refreshed = self.get_queryset().get(pk=record.pk)
        return Response(AttendanceRecordSerializer(refreshed, context={'request': request}).data, status=status.HTTP_200_OK)


class AttendanceBreakViewSet(_AttendanceAccessMixin, viewsets.ModelViewSet):
    serializer_class = AttendanceBreakSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['attendance']
    ordering_fields = ['break_in', 'created_at']

    def get_queryset(self):
        qs = AttendanceBreak.objects.select_related('attendance', 'attendance__client')
        if self._is_superadmin():
            client = self.request.query_params.get('client')
            if client:
                return qs.filter(attendance__client_id=client)
            return qs
        client_id = self._client_id()
        if not client_id:
            return AttendanceBreak.objects.none()
        return qs.filter(attendance__client_id=client_id)

