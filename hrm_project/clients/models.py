from django.db import models


class Client(models.Model):

    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=128, default='')
    schema_name = models.SlugField(max_length=63, unique=True, blank=True)
    schema_provisioned = models.BooleanField(default=False)
    enabled_addons = models.JSONField(default=list, blank=True)
    app_settings = models.JSONField(default=dict, blank=True)
    role_limit = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ClientRole(models.Model):
    BASE_ROLE_EMPLOYEE = 'employee'
    BASE_ROLE_HR = 'hr'
    BASE_ROLE_MANAGER = 'manager'
    BASE_ROLE_CHOICES = (
        (BASE_ROLE_EMPLOYEE, 'Employee'),
        (BASE_ROLE_HR, 'HR'),
        (BASE_ROLE_MANAGER, 'Manager'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    base_role = models.CharField(max_length=20, choices=BASE_ROLE_CHOICES, default=BASE_ROLE_EMPLOYEE)
    module_permissions = models.JSONField(default=list, blank=True)
    enabled_addons = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sort_order', 'name')
        unique_together = ('client', 'slug')

    def __str__(self):
        return f'{self.client_id}:{self.name}'
