from django.contrib import admin

from .models import Holiday


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('name', 'holiday_type', 'client', 'start_date', 'end_date', 'is_paid', 'is_active')
    list_filter = ('client', 'holiday_type', 'is_paid', 'is_active')
    search_fields = ('name', 'holiday_type', 'description')
