from datetime import timedelta

from rest_framework import serializers

from clients.models import Client
from .models import LeaveRequest, LeaveType


class LeaveTypeSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )

    class Meta:
        model = LeaveType
        fields = (
            'id',
            'client',
            'name',
            'max_days_per_year',
            'is_paid',
            'color',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        validators = []

    def _resolve_client_from_auth(self, request):
        if not request:
            return None
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        # First preference: user's profile client.
        try:
            profile = user.profile
            if profile and profile.client_id:
                return profile.client
        except Exception:
            pass

        # Fallback: client_id claim from JWT token.
        auth = getattr(request, 'auth', None)
        client_id = None
        try:
            if auth is not None:
                client_id = auth.get('client_id')
        except Exception:
            client_id = None
        if client_id:
            return Client.objects.filter(id=client_id).first()
        return None

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        resolved_client = self._resolve_client_from_auth(request)

        # Client users/admin should always use token/profile client automatically.
        if user and not user.is_superuser and resolved_client:
            attrs['client'] = resolved_client
            return attrs

        if user and not user.is_superuser and not resolved_client:
            raise serializers.ValidationError({'client': 'Client could not be resolved from your login token.'})

        # Superadmin can send client explicitly; if omitted, validation should fail.
        if not attrs.get('client') and not (user and user.is_superuser):
            raise serializers.ValidationError({'client': 'This field is required.'})

        target_client = attrs.get('client') or resolved_client
        target_name = str(attrs.get('name') or '').strip()
        if target_client and target_name:
            qs = LeaveType.objects.filter(client=target_client, name__iexact=target_name)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({'name': 'Leave type with this name already exists for this client.'})

        return attrs


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)
    manager_name = serializers.SerializerMethodField(read_only=True)
    hr_name = serializers.SerializerMethodField(read_only=True)
    can_review = serializers.SerializerMethodField(read_only=True)
    pending_with = serializers.SerializerMethodField(read_only=True)
    leave_type_is_paid = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = (
            'id',
            'client',
            'employee',
            'employee_name',
            'leave_type',
            'leave_type_is_paid',
            'leave_unit',
            'leave_hours',
            'start_date',
            'end_date',
            'total_days',
            'reason',
            'status',
            'manager',
            'manager_name',
            'manager_status',
            'manager_comment',
            'hr',
            'hr_name',
            'hr_status',
            'hr_comment',
            'can_review',
            'pending_with',
            'reviewer_comment',
            'applied_by',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'client',
            'total_days',
            'status',
            'manager',
            'manager_status',
            'hr_status',
            'hr',
            'manager_comment',
            'hr_comment',
            'reviewer_comment',
            'applied_by',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )

    def get_employee_name(self, obj):
        if not obj.employee_id:
            return ''
        return f'{obj.employee.first_name} {obj.employee.last_name}'.strip()

    def get_manager_name(self, obj):
        if not obj.manager_id:
            return ''
        return obj.manager.get_full_name() or obj.manager.username

    def get_hr_name(self, obj):
        if not obj.hr_id:
            return ''
        return obj.hr.get_full_name() or obj.hr.username

    def get_can_review(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if obj.status != LeaveRequest.STATUS_PENDING:
            return False

        if obj.manager_id == user.id and obj.manager_status == LeaveRequest.APPROVAL_PENDING:
            return True
        if obj.hr_id == user.id and obj.hr_status == LeaveRequest.APPROVAL_PENDING:
            return True
        return False

    def get_leave_type_is_paid(self, obj):
        if not obj.client_id or not obj.leave_type:
            return None

        # Cache lookup values per serializer instance to avoid repeated queries in list APIs.
        cache = self.context.setdefault('_leave_type_paid_cache', {})
        cache_key = (obj.client_id, obj.leave_type)
        if cache_key not in cache:
            leave_type = LeaveType.objects.filter(
                client_id=obj.client_id,
                name=obj.leave_type,
                is_active=True,
            ).only('is_paid').first()
            cache[cache_key] = (leave_type.is_paid if leave_type else None)
        return cache[cache_key]

    def get_pending_with(self, obj):
        if obj.status != LeaveRequest.STATUS_PENDING:
            return '-'
        pending_roles = []
        if obj.manager_status == LeaveRequest.APPROVAL_PENDING:
            pending_roles.append('Manager')
        if obj.hr_status == LeaveRequest.APPROVAL_PENDING:
            pending_roles.append('HR')
        if pending_roles:
            return ' / '.join(pending_roles)
        return '-'

    def validate(self, attrs):
        employee = attrs.get('employee') or getattr(self.instance, 'employee', None)
        start_date = attrs.get('start_date') or getattr(self.instance, 'start_date', None)
        end_date = attrs.get('end_date') or getattr(self.instance, 'end_date', None)
        leave_type_name = str(attrs.get('leave_type') or getattr(self.instance, 'leave_type', '')).strip()
        leave_unit = str(attrs.get('leave_unit') or getattr(self.instance, 'leave_unit', LeaveRequest.UNIT_DAY)).strip().lower()
        leave_hours = attrs.get('leave_hours', getattr(self.instance, 'leave_hours', None))

        if not employee:
            raise serializers.ValidationError({'employee': 'This field is required.'})
        if not start_date:
            raise serializers.ValidationError({'start_date': 'This field is required.'})
        if not end_date:
            raise serializers.ValidationError({'end_date': 'This field is required.'})
        if not leave_type_name:
            raise serializers.ValidationError({'leave_type': 'This field is required.'})
        if end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date must be same or after start date.'})
        if leave_unit not in (LeaveRequest.UNIT_DAY, LeaveRequest.UNIT_HOUR):
            raise serializers.ValidationError({'leave_unit': 'Leave unit must be day or hour.'})

        leave_type = LeaveType.objects.filter(
            client_id=employee.client_id,
            name=leave_type_name,
            is_active=True,
        ).only('id').first()
        if not leave_type:
            raise serializers.ValidationError({'leave_type': 'Select a valid active leave type.'})

        overlapping_qs = LeaveRequest.objects.filter(
            employee_id=employee.id,
            status__in=(LeaveRequest.STATUS_PENDING, LeaveRequest.STATUS_APPROVED),
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        if self.instance:
            overlapping_qs = overlapping_qs.exclude(id=self.instance.id)
        if overlapping_qs.exists():
            raise serializers.ValidationError(
                {'start_date': 'Leave already exists for one or more selected dates (pending/approved).'}
            )

        if leave_unit == LeaveRequest.UNIT_HOUR:
            if start_date != end_date:
                raise serializers.ValidationError({'end_date': 'Hourly leave must be for a single date.'})
            if leave_hours is None:
                raise serializers.ValidationError({'leave_hours': 'Leave hours are required for hourly leave.'})
            if leave_hours <= 0:
                raise serializers.ValidationError({'leave_hours': 'Leave hours must be greater than 0.'})
            if leave_hours > 3:
                raise serializers.ValidationError({'leave_hours': 'Maximum hourly leave is 3 hours in a day.'})
            attrs['total_days'] = 0
        else:
            attrs['leave_hours'] = None
            attrs['total_days'] = (end_date - start_date + timedelta(days=1)).days

        return attrs
