import os
import uuid
import json
import base64
import binascii
import mimetypes

from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
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

    @staticmethod
    def _file_from_base64(instance):
        raw_value = str(instance.file_base64 or '').strip()
        if not raw_value:
            return None, '', ''

        mime_type = str(instance.file_mime_type or '').strip()
        payload = raw_value
        if raw_value.startswith('data:') and ';base64,' in raw_value:
            header, payload = raw_value.split(',', 1)
            header_mime = header[5:].split(';', 1)[0].strip()
            if header_mime:
                mime_type = mime_type or header_mime

        try:
            file_bytes = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error):
            return None, '', ''

        if not file_bytes:
            return None, '', ''

        file_name = str(instance.file_name or '').strip() or f'document-{instance.id}'
        if not mime_type:
            guessed_type, _ = mimetypes.guess_type(file_name)
            mime_type = guessed_type or 'application/octet-stream'
        return file_bytes, file_name, mime_type

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        instance = self.get_object()
        file_bytes, file_name, mime_type = self._file_from_base64(instance)
        if file_bytes:
            response = HttpResponse(file_bytes, content_type=mime_type)
            response['Content-Disposition'] = f'inline; filename="{file_name}"'
            return response

        if not str(instance.file_url or '').strip():
            return Response({'detail': 'Document file not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Backward compatibility for legacy URL-based documents.
        return Response({'file_url': instance.file_url}, status=status.HTTP_200_OK)


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
            'requested_doc_types': req.requested_doc_types or [],
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

        allowed_doc_types = [str(item or '').strip() for item in (req.requested_doc_types or []) if str(item or '').strip()]
        flat_documents = []
        typed_documents = []

        request_documents = request.data.get('documents')
        parsed_documents = []
        if isinstance(request_documents, list):
            parsed_documents = request_documents
        elif isinstance(request_documents, str):
            raw_docs = request_documents.strip()
            if raw_docs:
                try:
                    loaded = json.loads(raw_docs)
                    if isinstance(loaded, list):
                        parsed_documents = loaded
                except Exception:
                    parsed_documents = []

        for item in parsed_documents:
            if not isinstance(item, dict):
                continue
            doc_type = str(item.get('doc_type') or '').strip()
            file_url = str(item.get('file_url') or '').strip()
            file_base64 = str(item.get('file_base64') or '').strip()
            file_name = str(item.get('file_name') or '').strip()
            file_mime_type = str(item.get('file_mime_type') or '').strip()
            if not file_url and not file_base64:
                continue
            if allowed_doc_types and doc_type not in allowed_doc_types:
                return Response(
                    {'documents': f'Invalid document type: {doc_type or "Unknown"}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            typed_documents.append({
                'doc_type': doc_type,
                'file_url': file_url,
                'file_base64': file_base64,
                'file_name': file_name,
                'file_mime_type': file_mime_type,
            })

        uploaded_files = request.FILES.getlist('files')
        if not uploaded_files:
            single_uploaded_file = request.FILES.get('file')
            if single_uploaded_file:
                uploaded_files = [single_uploaded_file]

        for uploaded_file in uploaded_files:
            file_name = str(uploaded_file.name or '').strip() or 'document'
            file_mime_type = str(getattr(uploaded_file, 'content_type', '') or '').strip()
            payload = base64.b64encode(uploaded_file.read()).decode('ascii')
            if not payload:
                continue
            flat_documents.append({
                'doc_type': '',
                'file_url': '',
                'file_base64': payload,
                'file_name': file_name,
                'file_mime_type': file_mime_type,
            })

        file_urls = []
        request_data_file_urls = request.data.get('file_urls')
        if isinstance(request_data_file_urls, (list, tuple)):
            for item in request_data_file_urls:
                value = str(item or '').strip()
                if value:
                    file_urls.append(value)
        elif isinstance(request_data_file_urls, str):
            raw = request_data_file_urls.strip()
            if raw:
                if raw.startswith('['):
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, list):
                            for item in parsed:
                                value = str(item or '').strip()
                                if value:
                                    file_urls.append(value)
                    except Exception:
                        pass
                elif ',' in raw:
                    for item in raw.split(','):
                        value = str(item or '').strip()
                        if value:
                            file_urls.append(value)
                else:
                    file_urls.append(raw)

        single_file_url = str(request.data.get('file_url') or '').strip()
        if single_file_url:
            file_urls.append(single_file_url)

        unique_file_urls = []
        for url in file_urls:
            if url not in unique_file_urls:
                unique_file_urls.append(url)
        file_urls = unique_file_urls

        if allowed_doc_types and (file_urls or not typed_documents):
            return Response(
                {'documents': 'Please select a valid document type for each uploaded file.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not file_urls and not typed_documents and not flat_documents:
            return Response({'file': 'Please attach at least one document.'}, status=status.HTTP_400_BAD_REQUEST)

        created_documents = []
        flat_documents = list(typed_documents) + flat_documents
        for file_url in file_urls:
            flat_documents.append({'doc_type': '', 'file_url': file_url, 'file_base64': '', 'file_name': '', 'file_mime_type': ''})

        for index, item in enumerate(flat_documents, start=1):
            file_url = str(item.get('file_url') or '').strip()
            file_base64 = str(item.get('file_base64') or '').strip()
            file_name = str(item.get('file_name') or '').strip()
            file_mime_type = str(item.get('file_mime_type') or '').strip()
            doc_type = str(item.get('doc_type') or '').strip()
            if doc_type:
                doc_title = f'{title} - {doc_type}'
            else:
                doc_title = title if len(flat_documents) == 1 else f'{title} ({index})'
            doc = Document.objects.create(
                client_id=req.client_id,
                title=doc_title,
                category=str(req.category or '').strip(),
                effective_date=None,
                status=Document.STATUS_PENDING,
                file_url=file_url,
                file_base64=file_base64,
                file_name=file_name,
                file_mime_type=file_mime_type,
                notes=str(req.notes or '').strip(),
                uploader_name=str(request.data.get('uploader_name') or '').strip(),
                uploader_email=str(req.request_email or '').strip(),
                uploaded_by=None,
                approved_by=None,
            )
            created_documents.append(doc)

        req.uploaded_document = created_documents[0]
        req.is_active = False
        req.save(update_fields=['uploaded_document', 'is_active', 'updated_at'])

        return Response(
            {
                'detail': f'{len(created_documents)} document(s) uploaded successfully.',
                'uploaded_count': len(created_documents),
                'document_ids': [doc.id for doc in created_documents],
                'document_id': created_documents[0].id,
            },
            status=status.HTTP_201_CREATED
        )
