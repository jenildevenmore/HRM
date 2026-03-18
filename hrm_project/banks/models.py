from django.db import models

from clients.models import Client
from employees.models import Employee


class BankAccount(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='bank_accounts')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=120)
    account_holder_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=30, blank=True, default='')
    branch_name = models.CharField(max_length=120, blank=True, default='')
    upi_id = models.CharField(max_length=120, blank=True, default='')
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('employee_id', 'bank_name')
        unique_together = ('client', 'employee', 'account_number')

    def __str__(self):
        return f'{self.client_id}:{self.employee_id}:{self.bank_name}'
