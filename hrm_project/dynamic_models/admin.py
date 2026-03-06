from django.contrib import admin

from .models import DynamicField, DynamicModel, DynamicRecord


@admin.register(DynamicModel)
class DynamicModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'name', 'slug', 'created_at')
    search_fields = ('name', 'slug', 'client__name')
    list_filter = ('client',)


@admin.register(DynamicField)
class DynamicFieldAdmin(admin.ModelAdmin):
    list_display = ('id', 'dynamic_model', 'name', 'key', 'field_type', 'required', 'sort_order')
    search_fields = ('name', 'key', 'dynamic_model__name')
    list_filter = ('field_type', 'required', 'dynamic_model__client')


@admin.register(DynamicRecord)
class DynamicRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'dynamic_model', 'created_at', 'updated_at')
    list_filter = ('dynamic_model__client', 'dynamic_model')
    search_fields = ('dynamic_model__name', 'dynamic_model__slug')

