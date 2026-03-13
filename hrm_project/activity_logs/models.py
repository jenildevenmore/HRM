from django.conf import settings
from django.db import models

from clients.models import Client


class ActivityLog(models.Model):
    ACTION_VIEW = 'view'
    ACTION_GET = 'get'
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CLICK = 'click'
    ACTION_OTHER = 'other'
    ACTION_CHOICES = (
        (ACTION_VIEW, 'View'),
        (ACTION_GET, 'Get'),
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
        (ACTION_CLICK, 'Click'),
        (ACTION_OTHER, 'Other'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='activity_logs', null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    actor_role = models.CharField(max_length=32, blank=True, default='')
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, default=ACTION_OTHER)
    module = models.CharField(max_length=64, blank=True, default='')
    path = models.CharField(max_length=255, blank=True, default='')
    method = models.CharField(max_length=12, blank=True, default='')
    status_code = models.PositiveIntegerField(default=200)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.actor_id}:{self.action}:{self.module}:{self.path}'
