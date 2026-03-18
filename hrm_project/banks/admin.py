from django.contrib import admin

from .models import BankAccount


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'client', 'employee', 'bank_name', 'account_holder_name',
        'account_number', 'ifsc_code', 'is_primary', 'is_active',
    )
    list_filter = ('client', 'is_primary', 'is_active')
    search_fields = ('bank_name', 'account_holder_name', 'account_number', 'ifsc_code', 'employee__first_name', 'employee__last_name')
