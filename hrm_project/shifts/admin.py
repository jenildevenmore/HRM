from django.contrib import admin

from .models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'client', 'name', 'code', 'start_time', 'end_time',
        'grace_minutes', 'is_night_shift', 'is_active',
    )
    list_filter = ('client', 'is_night_shift', 'is_active')
    search_fields = ('name', 'code', 'weekly_off', 'client__name')
