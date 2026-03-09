from django.db import models

from clients.models import Client


class Holiday(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=140)
    holiday_type = models.CharField(max_length=80, blank=True, default='')
    start_date = models.DateField()
    end_date = models.DateField()
    is_paid = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-start_date', 'name')
        unique_together = ('client', 'name', 'start_date')

    def __str__(self):
        return f'{self.client_id}:{self.name}:{self.start_date}'
