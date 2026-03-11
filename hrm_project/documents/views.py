import os
import uuid

from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import slugify
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, DocumentUploadRequest
from .serializers import DocumentSerializer, DocumentUploadRequestSerializer


class _DocumentAccessMixin:
    def _profile(self):
        try:
            return self.request.user.profile
        except Exception:
            return None

    def _is_superadmin(self):
        profile = self._profile()
        return self.request.user.is_superuser or bool(profile and profile.role == 'superadmin')

    def _client_id_from_auth(self):
        auth = getattr(self.request, 'auth', None)
        try:
            return auth.get('client_id') if auth is not None else None
        except Exception:
            return None

    def _client_id(self):
        profile = self._profile()
        if profile and profile.client_id:
            return profile.client_id
        return self._client_id_from_auth()


class DocumentViewSet(_DocumentAccessMixin, viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'category', 'status']
    search_fields = ['title', 'category', 'notes', 'uploader_name', 'uploader_email']
    ordering_fields = ['title', 'effective_date', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = Document.objects.select_related('client', 'uploaded_by', 'approved_by')
        if self._is_superadmin():
            return qs
        client_id = self._client_id()
        if not client_id:
            return Document.objects.none()
        return qs.filter(client_id=client_id)

    def perform_create(self, serializer):
        if self._is_superadmin():
            if not serializer.validated_data.get('client'):
                raise PermissionDenied('Client is required for superadmin.')
            serializer.save(uploaded_by=self.request.user)
            return

        client_id = self._client_id()
        if not client_id:
            raise PermissionDenied('User profile not found.')
        serializer.save(client_id=client_id, uploaded_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.instance
        if self._is_superadmin():
            serializer.save(client_id=instance.client_id)
            return

        client_id = self._client_id()
        if not client_id or client_id != instance.client_id:
            raise PermissionDenied('Not allowed for this client.')
        serializer.save(client_id=instance.client_id)

    def perform_destroy(self, instance):
        if self._is_superadmin():
            instance.delete()
            return

        client_id = self._client_id()
        if not client_id or client_id != instance.client_id:
            raise PermissionDenied('Not allowed for this client.')
        instance.delete()


class DocumentUploadRequestViewSet(_DocumentAccessMixin, viewsets.ModelViewSet):
    serializer_class = DocumentUploadRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'is_active', 'category']
    search_fields = ['title', 'category', 'request_email', 'notes']
    ordering_fields = ['title', 'expires_at', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = DocumentUploadRequest.objects.select_related('client', 'uploaded_document', 'created_by')
        if self._is_superadmin():
            return qs
        client_id = self._client_id()
        if not client_id:
            return DocumentUploadRequest.objects.none()
        return qs.filter(client_id=client_id)

    def perform_create(self, serializer):
        if self._is_superadmin():
            if not serializer.validated_data.get('client'):
                raise PermissionDenied('Client is required for superadmin.')
            serializer.save(created_by=self.request.user)
            return

        client_id = self._client_id()
        if not client_id:
            raise PermissionDenied('User profile not found.')
        serializer.save(client_id=client_id, created_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.instance
        if self._is_superadmin():
            serializer.save(client_id=instance.client_id)
            return

        client_id = self._client_id()
        if not client_id or client_id != instance.client_id:
            raise PermissionDenied('Not allowed for this client.')
        serializer.save(client_id=instance.client_id)

    def perform_destroy(self, instance):
        if self._is_superadmin():
            instance.delete()
            return

        client_id = self._client_id()
        if not client_id or client_id != instance.client_id:
            raise PermissionDenied('Not allowed for this client.')
        instance.delete()


class PublicDocumentUploadView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @staticmethod
    def _save_file(uploaded_file):
        ext = os.path.splitext(uploaded_file.name or '')[1].lower()
        base_name = slugify(os.path.splitext(uploaded_file.name or 'document')[0]) or 'document'
        stamp = timezone.now().strftime('%Y/%m')
        rel_path = f'documents/public/{stamp}/{base_name}-{uuid.uuid4().hex[:10]}{ext}'
        saved_path = default_storage.save(rel_path, uploaded_file)
        return default_storage.url(saved_path)

    def _request_obj(self, token):
        try:
            return DocumentUploadRequest.objects.select_related('client').get(token=token)
        except DocumentUploadRequest.DoesNotExist:
            return None

    def get(self, request, token):
        req = self._request_obj(token)
        if not req:
            return Response({'detail': 'Upload link is invalid.'}, status=status.HTTP_404_NOT_FOUND)
        if not req.is_active:
            return Response({'detail': 'Upload link is inactive.'}, status=status.HTTP_400_BAD_REQUEST)
        if req.is_expired:
            return Response({'detail': 'Upload link has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'title': req.title,
            'category': req.category,
            'notes': req.notes,
            'request_email': req.request_email,
            'expires_at': req.expires_at,
            'client_id': req.client_id,
        }, status=status.HTTP_200_OK)

    def post(self, request, token):
        req = self._request_obj(token)
        if not req:
            return Response({'detail': 'Upload link is invalid.'}, status=status.HTTP_404_NOT_FOUND)
        if not req.is_active:
            return Response({'detail': 'Upload link is inactive.'}, status=status.HTTP_400_BAD_REQUEST)
        if req.is_expired:
            return Response({'detail': 'Upload link has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        title = str(req.title or '').strip()
        if not title:
            return Response({'title': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = request.FILES.get('file')
        file_url = str(request.data.get('file_url') or '').strip()
        if uploaded_file:
            file_url = self._save_file(uploaded_file)
        if not file_url:
            return Response({'file': 'Please attach a document.'}, status=status.HTTP_400_BAD_REQUEST)

        doc = Document.objects.create(
            client_id=req.client_id,
            title=title,
            category=str(req.category or '').strip(),
            effective_date=None,
            status=Document.STATUS_PENDING,
            file_url=file_url,
            notes=str(req.notes or '').strip(),
            uploader_name=str(request.data.get('uploader_name') or '').strip(),
            uploader_email=str(req.request_email or '').strip(),
            uploaded_by=None,
            approved_by=None,
        )

        req.uploaded_document = doc
        req.is_active = False
        req.save(update_fields=['uploaded_document', 'is_active', 'updated_at'])

        return Response({'detail': 'Document uploaded successfully.', 'document_id': doc.id}, status=status.HTTP_201_CREATED)
