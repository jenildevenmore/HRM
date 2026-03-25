from django.db import models

from clients.models import Client
from employees.models import Employee
from shifts.models import Shift


class PayrollPolicy(models.Model):
    BASIS_DAY = 'day'
    BASIS_HOUR = 'hour'
    SALARY_BASIS_CHOICES = (
        (BASIS_DAY, 'Day'),
        (BASIS_HOUR, 'Hour'),
    )

    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='payroll_policy')
    monthly_working_days = models.PositiveIntegerField(default=24)
    standard_hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=8)
    salary_basis = models.CharField(max_length=10, choices=SALARY_BASIS_CHOICES, default=BASIS_DAY)
    allow_extra_hours_payout = models.BooleanField(default=False)
    allow_extra_days_payout = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('client_id',)

    def __str__(self):
        return f'PayrollPolicy(client={self.client_id}, days={self.monthly_working_days})'


class EmployeeCompensation(models.Model):
    BASIS_MONTHLY = 'monthly'
    BASIS_DAILY = 'daily'
    BASIS_HOURLY = 'hourly'
    SALARY_BASIS_CHOICES = (
        (BASIS_MONTHLY, 'Monthly'),
        (BASIS_DAILY, 'Daily'),
        (BASIS_HOURLY, 'Hourly'),
    )

    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='compensation')
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_compensations',
    )
    salary_basis = models.CharField(max_length=10, choices=SALARY_BASIS_CHOICES, default=BASIS_MONTHLY)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    daily_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hourly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('employee_id',)

    def __str__(self):
        return f'EmployeeCompensation(employee={self.employee_id}, salary={self.monthly_salary})'
