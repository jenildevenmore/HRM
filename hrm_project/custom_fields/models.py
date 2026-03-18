from django.db import models
from clients.models import Client
from employees.models import Employee


class CustomField(models.Model):

    FIELD_TYPES = (
        ("text", "Text"),
        ("number", "Number"),
        ("date", "Date"),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE)

    model_name = models.CharField(max_length=50)

    field_name = models.CharField(max_length=100)

    field_type = models.CharField(max_length=50, choices=FIELD_TYPES)

    def __str__(self):
        return self.field_name
    

class CustomFieldValue(models.Model):

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)

    field = models.ForeignKey(CustomField, on_delete=models.CASCADE)

    value = models.TextField()