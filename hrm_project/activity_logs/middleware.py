from django.conf import settings

from activity_logs.models import ActivityLog
import json


class ActivityLogMiddleware:
    """
    Lightweight audit logger for authenticated users.
    """

    SKIP_PREFIXES = (
        '/static/',
        '/media/',
        '/favicon.ico',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.app_prefix = str(getattr(settings, 'APP_URL_PREFIX', '') or '').rstrip('/')
        self.skip_paths = {
            self._prefix('/api/token/'),
            self._prefix('/api/token/refresh/'),
            self._prefix('/api/accounts/me/'),
            self._prefix('/api/activity-logs/'),
            self._prefix('/activity-logs/click/'),
        }

    def __call__(self, request):
        payload_data = self._extract_request_payload(request)
        resource_id = self._extract_resource_id(request.path or '')
        if not resource_id:
            resource_id = self._extract_resource_id_from_payload(payload_data)
        response = self.get_response(request)
        if not resource_id:
            resource_id = self._extract_resource_id_from_response(response)
        self._log(request, response, payload_data=payload_data, resource_id=resource_id)
        return response

    def _log(self, request, response, payload_data=None, resource_id=''):
        path = request.path or ''
        if any(path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return
        if path in self.skip_paths:
            return

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return

        method = (request.method or '').upper()
        is_api = path.startswith(self._prefix('/api/'))
        if method in ('HEAD', 'OPTIONS'):
            return

        # Keep logs useful and not too noisy.
        if (not is_api) and method not in ('GET',):
            return

        action = self._infer_action(method, path, is_api)

        module = self._infer_module(path)
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')

        profile = getattr(user, 'profile', None)
        client_id = getattr(profile, 'client_id', None)
        actor_role = str(getattr(profile, 'role', '') or '')
        metadata = self._build_metadata(
            action=action,
            client_id=client_id,
            module=module,
            path=path,
            resource_id=resource_id,
            payload_data=payload_data,
        )

        try:
            ActivityLog.objects.create(
                client_id=client_id,
                actor=user,
                actor_role=actor_role,
                action=action,
                module=module,
                path=path,
                method=method,
                status_code=getattr(response, 'status_code', 200) or 200,
                ip_address=ip,
                metadata=metadata,
            )
        except Exception:
            # Never break request flow because of logging.
            return

    def _infer_action(self, method, path, is_api):
        if method == 'GET':
            return ActivityLog.ACTION_GET if is_api else ActivityLog.ACTION_VIEW

        if method == 'POST':
            lowered = (path or '').lower()
            if '/delete/' in lowered or lowered.endswith('/delete'):
                return ActivityLog.ACTION_DELETE
            if '/edit/' in lowered or lowered.endswith('/edit'):
                return ActivityLog.ACTION_UPDATE
            if '/update/' in lowered or lowered.endswith('/update'):
                return ActivityLog.ACTION_UPDATE
            return ActivityLog.ACTION_CREATE

        if method in ('PUT', 'PATCH'):
            return ActivityLog.ACTION_UPDATE
        if method == 'DELETE':
            return ActivityLog.ACTION_DELETE
        return ActivityLog.ACTION_OTHER

    def _infer_module(self, path):
        clean = (path or '/').strip('/').split('/')
        if self.app_prefix:
            prefix_part = self.app_prefix.strip('/')
            if clean and clean[0] == prefix_part:
                clean = clean[1:]
        if not clean:
            return 'dashboard'
        if clean[0] == 'api' and len(clean) > 1:
            return clean[1]
        return clean[0]

    def _extract_request_payload(self, request):
        method = (request.method or '').upper()
        if method not in ('POST', 'PUT', 'PATCH'):
            return {}

        content_type = (request.META.get('CONTENT_TYPE') or '').lower()
        if 'application/json' in content_type:
            try:
                raw_body = (request.body or b'').decode('utf-8')
                if not raw_body.strip():
                    return {}
                parsed = json.loads(raw_body)
                return parsed if isinstance(parsed, dict) else {'data': parsed}
            except Exception:
                return {}

        data = {}
        try:
            if hasattr(request, 'POST'):
                data.update({k: request.POST.get(k) for k in request.POST.keys() if k != 'csrfmiddlewaretoken'})
        except Exception:
            pass
        try:
            if hasattr(request, 'FILES'):
                file_names = [getattr(f, 'name', '') for f in request.FILES.values() if getattr(f, 'name', '')]
                if file_names:
                    data['files'] = file_names
        except Exception:
            pass
        return data

    def _extract_resource_id(self, path):
        parts = [p for p in str(path or '').strip('/').split('/') if p]
        if self.app_prefix:
            prefix_part = self.app_prefix.strip('/')
            if parts and parts[0] == prefix_part:
                parts = parts[1:]
        if len(parts) >= 3 and parts[0] == 'api':
            return parts[2]
        if len(parts) >= 2:
            return parts[1]
        return ''

    def _prefix(self, path):
        clean = '/' + str(path or '').strip().lstrip('/')
        if self.app_prefix and clean.startswith(f'{self.app_prefix}/'):
            return clean
        if self.app_prefix:
            return f'{self.app_prefix}{clean}'
        return clean

    def _build_metadata(self, action, client_id, module, path, resource_id, payload_data):
        metadata = {}
        if resource_id:
            metadata['resource_id'] = resource_id

        if action in (ActivityLog.ACTION_CREATE, ActivityLog.ACTION_UPDATE) and payload_data:
            metadata['request_payload'] = payload_data

        if action == ActivityLog.ACTION_UPDATE:
            previous_payload = self._last_payload_for_resource(client_id, module, resource_id)
            if previous_payload:
                metadata['previous_payload'] = previous_payload

        return metadata

    def _last_payload_for_resource(self, client_id, module, resource_id):
        try:
            previous_logs = (
                ActivityLog.objects
                .filter(
                    client_id=client_id,
                    module=module,
                    action__in=(ActivityLog.ACTION_CREATE, ActivityLog.ACTION_UPDATE),
                )
                .exclude(metadata={})
                .order_by('-created_at')
                .only('metadata')
            )
            target_resource = str(resource_id or '').strip()
            for previous in previous_logs:
                metadata = previous.metadata if isinstance(previous.metadata, dict) else {}
                prev_payload = metadata.get('request_payload')
                if not isinstance(prev_payload, (dict, list)):
                    continue

                if target_resource:
                    prev_resource = str(metadata.get('resource_id') or '').strip()
                    if prev_resource != target_resource:
                        continue
                return prev_payload
            return {}
        except Exception:
            return {}

    def _extract_resource_id_from_payload(self, payload_data):
        if not isinstance(payload_data, dict):
            return ''
        for key in ('id', 'pk', 'employee_id'):
            value = payload_data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ''

    def _extract_resource_id_from_response(self, response):
        try:
            if not response:
                return ''
            status_code = int(getattr(response, 'status_code', 0) or 0)
            if status_code < 200 or status_code >= 300:
                return ''
            content_type = str(response.get('Content-Type', '')).lower()
            if 'application/json' not in content_type:
                return ''
            raw_content = getattr(response, 'content', b'') or b''
            payload = json.loads(raw_content.decode('utf-8'))
            if isinstance(payload, dict):
                for key in ('id', 'pk', 'employee_id'):
                    value = payload.get(key)
                    if value is not None and str(value).strip():
                        return str(value).strip()
            return ''
        except Exception:
            return ''
