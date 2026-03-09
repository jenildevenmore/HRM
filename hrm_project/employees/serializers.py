from rest_framework import serializers
from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    hr_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            'id',
            'client',
            'first_name',
            'last_name',
            'email',
            'role',
            'role_display',
            'hr',
            'hr_name',
            'manager',
            'manager_name',
            'joining_date',
        )

    def get_hr_name(self, obj):
        if not obj.hr:
            return ''
        return f'{obj.hr.first_name} {obj.hr.last_name}'.strip()

    def get_manager_name(self, obj):
        if not obj.manager:
            return ''
        return f'{obj.manager.first_name} {obj.manager.last_name}'.strip()

    def validate(self, attrs):
        hr = attrs.get('hr', getattr(self.instance, 'hr', None))
        manager = attrs.get('manager', getattr(self.instance, 'manager', None))
        client = attrs.get('client', getattr(self.instance, 'client', None))
        current_employee = self.instance

        if hr:
            if hr.role != Employee.ROLE_HR:
                raise serializers.ValidationError({'hr': 'Selected employee must have HR role.'})
            if client and hr.client_id != client.id:
                raise serializers.ValidationError({'hr': 'HR must belong to the same client.'})
            if current_employee and hr.id == current_employee.id:
                raise serializers.ValidationError({'hr': 'Employee cannot be their own HR.'})

        if manager:
            if manager.role != Employee.ROLE_MANAGER:
                raise serializers.ValidationError({'manager': 'Selected employee must have Manager role.'})
            if client and manager.client_id != client.id:
                raise serializers.ValidationError({'manager': 'Manager must belong to the same client.'})
            if current_employee and manager.id == current_employee.id:
                raise serializers.ValidationError({'manager': 'Employee cannot be their own manager.'})

        return attrs
