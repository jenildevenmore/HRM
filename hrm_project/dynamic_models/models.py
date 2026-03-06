from django.db import models
from clients.models import Client
from employees.models import Employee


class DynamicModel(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='dynamic_models')
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    show_in_employee_form = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('client', 'slug')
        ordering = ('name',)

    def __str__(self):
        return f'{self.client_id}:{self.name}'


class DynamicField(models.Model):
    FIELD_TYPES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Boolean'),
        ('email', 'Email'),
    )

    dynamic_model = models.ForeignKey(
        DynamicModel,
        on_delete=models.CASCADE,
        related_name='fields',
    )
    name = models.CharField(max_length=120)
    key = models.SlugField(max_length=140)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    required = models.BooleanField(default=False)
    visible_to_users = models.BooleanField(default=True)
    choices_json = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('dynamic_model', 'key')
        ordering = ('sort_order', 'id')

    def __str__(self):
        return f'{self.dynamic_model.slug}.{self.key}'


class DynamicRecord(models.Model):
    dynamic_model = models.ForeignKey(
        DynamicModel,
        on_delete=models.CASCADE,
        related_name='records',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='dynamic_records',
        null=True,
        blank=True,
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.dynamic_model.slug}#{self.id}'
