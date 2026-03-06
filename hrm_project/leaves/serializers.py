from datetime import timedelta

from rest_framework import serializers

from .models import LeaveRequest


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)
    manager_name = serializers.SerializerMethodField(read_only=True)
    hr_name = serializers.SerializerMethodField(read_only=True)
    can_review = serializers.SerializerMethodField(read_only=True)
    pending_with = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = (
            'id',
            'client',
            'employee',
            'employee_name',
            'leave_type',
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
            'manager_status',
            'hr_status',
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

        profile = getattr(user, 'profile', None)
        is_admin = bool(user.is_superuser or (profile and profile.role in ('superadmin', 'admin')))
        if is_admin:
            return True

        if obj.manager_id == user.id and obj.manager_status == LeaveRequest.APPROVAL_PENDING:
            return True
        if (
            obj.hr_id == user.id
            and obj.manager_status == LeaveRequest.APPROVAL_APPROVED
            and obj.hr_status == LeaveRequest.APPROVAL_PENDING
        ):
            return True
        return False

    def get_pending_with(self, obj):
        if obj.status != LeaveRequest.STATUS_PENDING:
            return '-'
        if obj.manager_status == LeaveRequest.APPROVAL_PENDING:
            return 'Manager'
        if obj.hr_status == LeaveRequest.APPROVAL_PENDING:
            return 'HR'
        return '-'

    def validate(self, attrs):
        employee = attrs.get('employee') or getattr(self.instance, 'employee', None)
        start_date = attrs.get('start_date') or getattr(self.instance, 'start_date', None)
        end_date = attrs.get('end_date') or getattr(self.instance, 'end_date', None)
        manager = attrs.get('manager') or getattr(self.instance, 'manager', None)
        hr = attrs.get('hr') or getattr(self.instance, 'hr', None)

        if not employee:
            raise serializers.ValidationError({'employee': 'This field is required.'})
        if not start_date:
            raise serializers.ValidationError({'start_date': 'This field is required.'})
        if not end_date:
            raise serializers.ValidationError({'end_date': 'This field is required.'})
        if not manager:
            raise serializers.ValidationError({'manager': 'Manager is required.'})
        if not hr:
            raise serializers.ValidationError({'hr': 'HR is required.'})
        if manager.id == hr.id:
            raise serializers.ValidationError({'hr': 'Manager and HR must be different users.'})
        if end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date must be same or after start date.'})

        for label, user_obj in (('manager', manager), ('hr', hr)):
            try:
                profile = user_obj.profile
            except Exception:
                profile = None
            if not profile or profile.client_id != employee.client_id:
                raise serializers.ValidationError({label: f'{label.upper()} user must belong to the same client as employee.'})

        attrs['total_days'] = (end_date - start_date + timedelta(days=1)).days
        return attrs
