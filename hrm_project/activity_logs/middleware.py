from activity_logs.models import ActivityLog


class ActivityLogMiddleware:
    """
    Lightweight audit logger:
    - Logs page views for non-API GET requests
    - Logs create/update/delete actions for API non-GET requests
    """

    SKIP_PREFIXES = (
        '/static/',
        '/media/',
        '/favicon.ico',
    )
    SKIP_PATHS = {
        '/api/token/',
        '/api/token/refresh/',
        '/api/accounts/me/',
        '/api/activity-logs/',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self._log(request, response)
        return response

    def _log(self, request, response):
        path = request.path or ''
        if any(path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return
        if path in self.SKIP_PATHS:
            return

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return

        method = (request.method or '').upper()
        is_api = path.startswith('/api/')

        # Keep logs useful and not too noisy.
        if is_api and method == 'GET':
            return
        if (not is_api) and method != 'GET':
            return

        if method == 'GET':
            action = ActivityLog.ACTION_VIEW
        elif method == 'POST':
            action = ActivityLog.ACTION_CREATE
        elif method in ('PUT', 'PATCH'):
            action = ActivityLog.ACTION_UPDATE
        elif method == 'DELETE':
            action = ActivityLog.ACTION_DELETE
        else:
            action = ActivityLog.ACTION_OTHER

        module = self._infer_module(path)
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')

        profile = getattr(user, 'profile', None)
        client_id = getattr(profile, 'client_id', None)
        actor_role = str(getattr(profile, 'role', '') or '')

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
                metadata={},
            )
        except Exception:
            # Never break request flow because of logging.
            return

    def _infer_module(self, path):
        clean = (path or '/').strip('/').split('/')
        if not clean:
            return 'dashboard'
        if clean[0] == 'api' and len(clean) > 1:
            return clean[1]
        return clean[0]
