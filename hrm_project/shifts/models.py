from django.db import models

from clients.models import Client


class Shift(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, blank=True, default='')
    start_time = models.TimeField()
    end_time = models.TimeField()
    grace_minutes = models.PositiveIntegerField(default=0)
    is_night_shift = models.BooleanField(default=False)
    weekly_off = models.CharField(max_length=60, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        unique_together = ('client', 'name')

    def __str__(self):
        return f'{self.client_id}:{self.name}'
