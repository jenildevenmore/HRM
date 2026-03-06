from django.db import models


class Client(models.Model):

    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=128, default='')
    schema_name = models.SlugField(max_length=63, unique=True, blank=True)
    schema_provisioned = models.BooleanField(default=False)
    enabled_addons = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
