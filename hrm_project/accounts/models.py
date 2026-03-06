from django.db import models
from django.contrib.auth.models import User
from clients.models import Client


class ClientPermissionGroup(models.Model):
    name = models.CharField(max_length=120)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='permission_groups')
    module_permissions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('client', 'name')
        verbose_name = 'Client Permission Group'
        verbose_name_plural = 'Client Permission Groups'

    def __str__(self):
        return f'{self.client_id}:{self.name}'


class UserProfile(models.Model):
    """Extended user profile that links users to clients"""
    MODULE_PERMISSION_CHOICES = (
        ('employees', 'Employees'),
        ('attendance', 'Attendance'),
        ('custom_fields', 'Custom Fields'),
        ('dynamic_models', 'Dynamic Models'),
    )
    
    USER_ROLES = (
        ('superadmin', 'Super Admin'),
        ('admin', 'Client Admin'),
        ('employee', 'Employee'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    role = models.CharField(max_length=20, choices=USER_ROLES, default='employee')
    module_permissions = models.JSONField(default=list, blank=True)
    permission_group = models.ForeignKey(
        ClientPermissionGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
