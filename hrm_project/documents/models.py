import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from clients.models import Client


class Document(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=120, blank=True, default='')
    effective_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    file_url = models.CharField(max_length=600, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    uploader_name = models.CharField(max_length=150, blank=True, default='')
    uploader_email = models.EmailField(blank=True, default='')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_documents',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.client_id}:{self.title}'


class DocumentUploadRequest(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='document_upload_requests')
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=120, blank=True, default='')
    request_email = models.EmailField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    requested_doc_types = models.JSONField(default=list, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    uploaded_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_requests',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_document_upload_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.client_id}:{self.title}:{self.token}'

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())
