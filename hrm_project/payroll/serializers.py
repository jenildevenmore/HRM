from decimal import Decimal

from rest_framework import serializers

from clients.models import Client
from shifts.models import Shift
from .models import EmployeeCompensation, PayrollPolicy


class PayrollPolicySerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )

    class Meta:
        model = PayrollPolicy
        fields = (
            'id',
            'client',
            'monthly_working_days',
            'standard_hours_per_day',
            'salary_basis',
            'allow_extra_hours_payout',
            'allow_extra_days_payout',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_monthly_working_days(self, value):
        if value < 1 or value > 31:
            raise serializers.ValidationError('monthly_working_days must be between 1 and 31.')
        return value

    def validate_standard_hours_per_day(self, value):
        if value <= 0 or value > Decimal('24'):
            raise serializers.ValidationError('standard_hours_per_day must be between 0 and 24.')
        return value

    def _resolve_client_from_auth(self, request):
        if not request:
            return None
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        try:
            profile = user.profile
            if profile and profile.client_id:
                return profile.client
        except Exception:
            pass

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

        if user and not user.is_superuser and resolved_client:
            attrs['client'] = resolved_client
        elif user and not user.is_superuser and not resolved_client:
            raise serializers.ValidationError({'client': 'Client could not be resolved from your login token.'})

        if not attrs.get('client') and not (user and user.is_superuser):
            raise serializers.ValidationError({'client': 'This field is required.'})

        return attrs


class EmployeeCompensationSerializer(serializers.ModelSerializer):
    shift = serializers.PrimaryKeyRelatedField(
        queryset=Shift.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = EmployeeCompensation
        fields = (
            'id',
            'employee',
            'shift',
            'salary_basis',
            'monthly_salary',
            'daily_salary',
            'hourly_salary',
            'effective_from',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_monthly_salary(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('monthly_salary cannot be negative.')
        return value

    def validate_daily_salary(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('daily_salary cannot be negative.')
        return value

    def validate_hourly_salary(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('hourly_salary cannot be negative.')
        return value

    def validate(self, attrs):
        employee = attrs.get('employee', getattr(self.instance, 'employee', None))
        shift = attrs.get('shift', getattr(self.instance, 'shift', None))
        if employee and shift and employee.client_id != shift.client_id:
            raise serializers.ValidationError({'shift': 'Shift must belong to the same client as employee.'})

        basis = attrs.get('salary_basis', getattr(self.instance, 'salary_basis', EmployeeCompensation.BASIS_MONTHLY))
        monthly_salary = attrs.get('monthly_salary', getattr(self.instance, 'monthly_salary', None))
        daily_salary = attrs.get('daily_salary', getattr(self.instance, 'daily_salary', None))
        hourly_salary = attrs.get('hourly_salary', getattr(self.instance, 'hourly_salary', None))

        if basis == EmployeeCompensation.BASIS_MONTHLY and (monthly_salary is None):
            raise serializers.ValidationError({'monthly_salary': 'monthly_salary is required for monthly basis.'})
        if basis == EmployeeCompensation.BASIS_DAILY and (daily_salary is None):
            raise serializers.ValidationError({'daily_salary': 'daily_salary is required for daily basis.'})
        if basis == EmployeeCompensation.BASIS_HOURLY and (hourly_salary is None):
            raise serializers.ValidationError({'hourly_salary': 'hourly_salary is required for hourly basis.'})
        return attrs
