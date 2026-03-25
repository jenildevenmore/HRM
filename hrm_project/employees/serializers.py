from rest_framework import serializers
from .models import Employee
from clients.models import ClientRole


class EmployeeSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    client_role_name = serializers.CharField(source='client_role.name', read_only=True)
    client_role_base = serializers.CharField(source='client_role.base_role', read_only=True)
    hr_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    client_role = serializers.PrimaryKeyRelatedField(
        queryset=ClientRole.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Employee
        fields = (
            'id',
            'employee_code',
            'client',
            'first_name',
            'last_name',
            'email',
            'role',
            'role_display',
            'client_role',
            'client_role_name',
            'client_role_base',
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
        client_role = attrs.get('client_role', getattr(self.instance, 'client_role', None))
        role = attrs.get('role', getattr(self.instance, 'role', Employee.ROLE_EMPLOYEE))
        hr = attrs.get('hr', getattr(self.instance, 'hr', None))
        manager = attrs.get('manager', getattr(self.instance, 'manager', None))
        client = attrs.get('client', getattr(self.instance, 'client', None))
        current_employee = self.instance

        if self.instance is None and client and 'role_management' in (client.enabled_addons or []) and not client_role:
            raise serializers.ValidationError({'client_role': 'Create/select a client role first.'})

        if client_role:
            if client and client_role.client_id != client.id:
                raise serializers.ValidationError({'client_role': 'Selected role must belong to the same client.'})
            attrs['role'] = client_role.base_role
            role = client_role.base_role
        elif role not in (Employee.ROLE_EMPLOYEE, Employee.ROLE_HR, Employee.ROLE_MANAGER):
            raise serializers.ValidationError({'role': 'Invalid role.'})

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

        if role == Employee.ROLE_HR:
            attrs['manager'] = None
        elif role == Employee.ROLE_MANAGER:
            attrs['hr'] = None

        return attrs
