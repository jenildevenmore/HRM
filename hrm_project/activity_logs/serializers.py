from rest_framework import serializers

from .models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = (
            'id',
            'client',
            'actor',
            'actor_username',
            'actor_role',
            'action',
            'module',
            'path',
            'method',
            'status_code',
            'ip_address',
            'metadata',
            'created_at',
        )
        read_only_fields = fields

    def get_actor_username(self, obj):
        if not obj.actor_id:
            return ''
        return obj.actor.username
