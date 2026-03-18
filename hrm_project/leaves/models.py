from django.conf import settings
from django.db import models

from clients.models import Client
from employees.models import Employee


class LeaveType(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='leave_types')
    name = models.CharField(max_length=80)
    max_days_per_year = models.PositiveIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    color = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        unique_together = ('client', 'name')

    def __str__(self):
        return f'{self.client_id}:{self.name}'


class LeaveRequest(models.Model):
    APPROVAL_PENDING = 'pending'
    APPROVAL_APPROVED = 'approved'
    APPROVAL_REJECTED = 'rejected'
    APPROVAL_STATUS_CHOICES = (
        (APPROVAL_PENDING, 'Pending'),
        (APPROVAL_APPROVED, 'Approved'),
        (APPROVAL_REJECTED, 'Rejected'),
    )

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    )
    UNIT_DAY = 'day'
    UNIT_HOUR = 'hour'
    UNIT_HALF_DAY = 'half_day'
    LEAVE_UNIT_CHOICES = (
        (UNIT_DAY, 'Day'),
        (UNIT_HALF_DAY, 'Half Day'),
        (UNIT_HOUR, 'Hour'),
    )
    HALF_FIRST = 'first_half'
    HALF_SECOND = 'second_half'
    HALF_DAY_SLOT_CHOICES = (
        (HALF_FIRST, 'First Half'),
        (HALF_SECOND, 'Second Half'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='leave_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=60, default='Casual')
    leave_unit = models.CharField(max_length=10, choices=LEAVE_UNIT_CHOICES, default=UNIT_DAY)
    half_day_slot = models.CharField(max_length=20, choices=HALF_DAY_SLOT_CHOICES, blank=True, default='')
    leave_hours = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    leave_start_time = models.TimeField(null=True, blank=True)
    leave_end_time = models.TimeField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manager_leave_requests',
    )
    hr = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hr_leave_requests',
    )
    manager_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default=APPROVAL_PENDING,
    )
    hr_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default=APPROVAL_PENDING,
    )
    manager_comment = models.TextField(blank=True, default='')
    hr_comment = models.TextField(blank=True, default='')
    reviewer_comment = models.TextField(blank=True, default='')
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applied_leave_requests',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leave_requests',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.employee_id}:{self.leave_type}:{self.start_date}'
