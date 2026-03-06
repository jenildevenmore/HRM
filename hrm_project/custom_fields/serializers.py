from rest_framework import serializers
from .models import CustomField, CustomFieldValue


class CustomFieldSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomField
        fields = "__all__"


class CustomFieldValueSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomFieldValue
        fields = "__all__"