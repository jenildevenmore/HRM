from django.db import models

from clients.models import Client
from employees.models import Employee
from shifts.models import Shift


class AttendanceRecord(models.Model):
    STATUS_PRESENT = 'present'
    STATUS_ABSENT = 'absent'
    STATUS_LEAVE = 'leave'
    STATUS_HALF_DAY = 'half-day'
    STATUS_CHOICES = (
        (STATUS_PRESENT, 'Present'),
        (STATUS_ABSENT, 'Absent'),
        (STATUS_LEAVE, 'Leave'),
        (STATUS_HALF_DAY, 'Half Day'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='attendance_records')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    attendance_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_records',
    )
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-attendance_date', '-id')
        unique_together = ('employee', 'attendance_date')
        indexes = [
            models.Index(fields=['client', 'attendance_date']),
            models.Index(fields=['employee', 'attendance_date']),
        ]

    def __str__(self):
        return f'AttendanceRecord(emp={self.employee_id}, date={self.attendance_date})'


class AttendanceBreak(models.Model):
    attendance = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='breaks')
    break_in = models.TimeField()
    break_out = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('break_in', 'id')
        indexes = [
            models.Index(fields=['attendance']),
            models.Index(fields=['attendance', 'break_out']),
        ]

    def __str__(self):
        return f'AttendanceBreak(attendance={self.attendance_id}, in={self.break_in}, out={self.break_out})'

