from django.db import models
from clients.models import Client, ClientRole


class Employee(models.Model):
    ROLE_EMPLOYEE = 'employee'
    ROLE_HR = 'hr'
    ROLE_MANAGER = 'manager'
    ROLE_CHOICES = (
        (ROLE_EMPLOYEE, 'Employee'),
        (ROLE_HR, 'HR'),
        (ROLE_MANAGER, 'Manager'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_EMPLOYEE)
    client_role = models.ForeignKey(
        ClientRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    hr = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_employees_as_hr',
    )
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_employees_as_manager',
    )

    employee_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    joining_date = models.DateField()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if (creating or not self.employee_code) and self.pk:
            generated = f'EMP{self.pk:05d}'
            if self.employee_code != generated:
                self.employee_code = generated
                super().save(update_fields=['employee_code'])

    def __str__(self):
        return self.first_name
