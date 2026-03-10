from django.conf import settings
from django.db import models

from clients.models import Client


class CompanyPolicy(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='company_policies')
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, blank=True, default='')
    content = models.TextField(blank=True, default='')
    image_url = models.CharField(max_length=500, blank=True, default='')
    document_url = models.CharField(max_length=500, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_company_policies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        unique_together = ('client', 'title')

    def __str__(self):
        return f'{self.client_id}:{self.title}'
