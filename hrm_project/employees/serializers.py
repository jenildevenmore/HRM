from rest_framework import serializers
from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

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
            'joining_date',
        )
