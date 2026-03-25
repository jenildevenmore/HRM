import datetime

from rest_framework import serializers

from .models import AttendanceBreak, AttendanceRecord


class AttendanceBreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceBreak
        fields = ('id', 'break_in', 'break_out', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class AttendanceRecordSerializer(serializers.ModelSerializer):
    breaks = AttendanceBreakSerializer(many=True, read_only=True)
    break_sessions = serializers.ListField(child=serializers.DictField(), required=False, write_only=True)
    total_break_time = serializers.SerializerMethodField()
    total_time = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    shift_name = serializers.CharField(source='shift.name', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = (
            'id',
            'client',
            'employee',
            'employee_name',
            'attendance_date',
            'status',
            'shift',
            'shift_name',
            'check_in',
            'check_out',
            'remarks',
            'breaks',
            'break_sessions',
            'total_break_time',
            'total_time',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'client',
            'employee_name',
            'shift_name',
            'breaks',
            'total_break_time',
            'total_time',
            'created_at',
            'updated_at',
        )

    def get_employee_name(self, obj):
        return f'{obj.employee.first_name} {obj.employee.last_name}'.strip()

    def _duration_hms(self, seconds):
        total = max(0, int(seconds))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f'{h:02d}:{m:02d}:{s:02d}'

    def _break_seconds(self, obj):
        total = 0
        for item in obj.breaks.all():
            if not item.break_out:
                continue
            start = datetime.datetime.combine(datetime.date.today(), item.break_in)
            end = datetime.datetime.combine(datetime.date.today(), item.break_out)
            if end < start:
                end += datetime.timedelta(days=1)
            total += max(0, int((end - start).total_seconds()))
        return total

    def get_total_break_time(self, obj):
        return self._duration_hms(self._break_seconds(obj))

    def get_total_time(self, obj):
        if not obj.check_in or not obj.check_out:
            return ''
        start = datetime.datetime.combine(datetime.date.today(), obj.check_in)
        end = datetime.datetime.combine(datetime.date.today(), obj.check_out)
        if end < start:
            end += datetime.timedelta(days=1)
        gross = int((end - start).total_seconds())
        net = max(0, gross - self._break_seconds(obj))
        return self._duration_hms(net)

    def validate(self, attrs):
        employee = attrs.get('employee') or getattr(self.instance, 'employee', None)
        attendance_date = attrs.get('attendance_date') or getattr(self.instance, 'attendance_date', None)
        if employee and attendance_date:
            q = AttendanceRecord.objects.filter(employee=employee, attendance_date=attendance_date)
            if self.instance:
                q = q.exclude(pk=self.instance.pk)
            if q.exists():
                raise serializers.ValidationError({'attendance_date': 'Attendance already exists for this employee on this date.'})
        return attrs

    def _sync_breaks(self, instance, break_sessions):
        if not isinstance(break_sessions, list):
            return
        rows = []
        for row in break_sessions:
            if not isinstance(row, dict):
                continue
            raw_in = str(row.get('break_in') or '').strip()
            raw_out = str(row.get('break_out') or '').strip()
            if not raw_in:
                continue
            try:
                break_in = datetime.time.fromisoformat(raw_in)
            except ValueError:
                continue
            break_out = None
            if raw_out:
                try:
                    break_out = datetime.time.fromisoformat(raw_out)
                except ValueError:
                    break_out = None
            rows.append((break_in, break_out))

        AttendanceBreak.objects.filter(attendance=instance).delete()
        AttendanceBreak.objects.bulk_create([
            AttendanceBreak(attendance=instance, break_in=bi, break_out=bo)
            for bi, bo in rows
        ])

    def create(self, validated_data):
        break_sessions = validated_data.pop('break_sessions', None)
        instance = super().create(validated_data)
        self._sync_breaks(instance, break_sessions)
        return instance

    def update(self, instance, validated_data):
        break_sessions = validated_data.pop('break_sessions', None)
        instance = super().update(instance, validated_data)
        self._sync_breaks(instance, break_sessions)
        return instance

