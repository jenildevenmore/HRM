from decimal import Decimal

from rest_framework import serializers

from .models import EmployeeCompensation, PayrollPolicy


class PayrollPolicySerializer(serializers.ModelSerializer):
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


class EmployeeCompensationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeCompensation
        fields = (
            'id',
            'employee',
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
