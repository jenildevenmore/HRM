from rest_framework import serializers

from clients.models import Client
from employees.models import Employee
from .models import BankAccount


class BankAccountSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BankAccount
        fields = (
            'id',
            'client',
            'employee',
            'employee_name',
            'bank_name',
            'account_holder_name',
            'account_number',
            'ifsc_code',
            'branch_name',
            'upi_id',
            'is_primary',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')
        validators = []

    def get_employee_name(self, obj):
        if not obj.employee:
            return ''
        return f"{obj.employee.first_name} {obj.employee.last_name}".strip()

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

        target_client = attrs.get('client') or getattr(self.instance, 'client', None) or resolved_client
        employee = attrs.get('employee') or getattr(self.instance, 'employee', None)
        if employee and target_client and employee.client_id != target_client.id:
            raise serializers.ValidationError({'employee': 'Employee must belong to the same client.'})

        account_number = str(attrs.get('account_number') or getattr(self.instance, 'account_number', '')).strip()
        if not account_number:
            raise serializers.ValidationError({'account_number': 'This field is required.'})

        if target_client and employee and account_number:
            qs = BankAccount.objects.filter(
                client=target_client,
                employee=employee,
                account_number=account_number,
            )
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({'account_number': 'Bank account already exists for this employee.'})

        return attrs
