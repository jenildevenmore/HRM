from rest_framework import serializers

from clients.models import Client

from .models import Document, DocumentUploadRequest


class DocumentSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)

    class Meta:
        model = Document
        fields = (
            'id',
            'client',
            'title',
            'category',
            'effective_date',
            'status',
            'file_url',
            'notes',
            'uploader_name',
            'uploader_email',
            'uploaded_by',
            'uploaded_by_username',
            'approved_by',
            'approved_by_username',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'uploaded_by',
            'uploaded_by_username',
            'approved_by_username',
            'created_at',
            'updated_at',
        )

    def validate(self, attrs):
        title = str(attrs.get('title') or '').strip()
        if not title:
            raise serializers.ValidationError({'title': 'This field is required.'})
        return attrs


class DocumentUploadRequestSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        required=False,
    )
    upload_url = serializers.SerializerMethodField(read_only=True)
    uploaded_document_title = serializers.CharField(source='uploaded_document.title', read_only=True)

    class Meta:
        model = DocumentUploadRequest
        fields = (
            'id',
            'client',
            'title',
            'category',
            'request_email',
            'notes',
            'token',
            'upload_url',
            'expires_at',
            'is_active',
            'uploaded_document',
            'uploaded_document_title',
            'created_by',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'token',
            'upload_url',
            'uploaded_document',
            'uploaded_document_title',
            'created_by',
            'created_at',
            'updated_at',
        )

    def get_upload_url(self, obj):
        request = self.context.get('request')
        if not request:
            return ''
        return request.build_absolute_uri(f'/document-upload/{obj.token}/')

    def validate(self, attrs):
        title = str(attrs.get('title') or '').strip()
        if not title:
            raise serializers.ValidationError({'title': 'This field is required.'})
        return attrs
