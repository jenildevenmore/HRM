from django.db import models
from clients.models import Client


class Employee(models.Model):

    client = models.ForeignKey(Client, on_delete=models.CASCADE)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()

    joining_date = models.DateField()

    def __str__(self):
        return self.first_name