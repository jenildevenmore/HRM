from django.db import models
from clients.models import Client


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

    joining_date = models.DateField()

    def __str__(self):
        return self.first_name
