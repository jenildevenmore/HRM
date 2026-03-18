from rest_framework import serializers
from django.conf import settings

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
            'file_name',
            'file_mime_type',
            'file_base64',
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
        extra_kwargs = {
            'file_base64': {'write_only': True},
        }

    def validate(self, attrs):
        title = str(attrs.get('title') or '').strip()
        if not title:
            raise serializers.ValidationError({'title': 'This field is required.'})
        raw_base64 = str(attrs.get('file_base64') or '').strip()
        if raw_base64:
            attrs['file_base64'] = raw_base64
            attrs['file_url'] = ''
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
            'requested_doc_types',
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
        app_prefix = str(getattr(settings, 'APP_URL_PREFIX', '') or '').rstrip('/')
        return request.build_absolute_uri(f'{app_prefix}/document-upload/{obj.token}/')

    def validate(self, attrs):
        title = str(attrs.get('title') or '').strip()
        if not title:
            raise serializers.ValidationError({'title': 'This field is required.'})
        requested_doc_types = attrs.get('requested_doc_types')
        if requested_doc_types is not None:
            if not isinstance(requested_doc_types, list):
                raise serializers.ValidationError({'requested_doc_types': 'Provide a list of document types.'})
            cleaned = []
            for item in requested_doc_types:
                value = str(item or '').strip()
                if not value:
                    continue
                if value not in cleaned:
                    cleaned.append(value)
            attrs['requested_doc_types'] = cleaned[:20]
        return attrs
