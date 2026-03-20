from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

APP_PREFIX = str(getattr(settings, 'APP_URL_PREFIX', '') or '').rstrip('/')
APP_PREFIX_WITH_SLASH = f'{APP_PREFIX}/' if APP_PREFIX else '/'


def _prefixed(path):
    clean = '/' + str(path or '').strip().lstrip('/')
    if APP_PREFIX and clean.startswith(APP_PREFIX_WITH_SLASH):
        return clean
    if APP_PREFIX:
        return f'{APP_PREFIX}{clean}'
    return clean


# URLs that do NOT require authentication
PUBLIC_URLS = [_prefixed('/login/'), _prefixed('/logout/'), _prefixed('/forgot-password/'), _prefixed('/reset-password/')]
PUBLIC_PREFIXES = (
    _prefixed('/api/'),
    '/admin/',
    '/static/',
    '/media/',
    _prefixed('/document-upload/'),
    '/favicon.ico',
)
DEMO_ALLOWED_PATHS = (
    _prefixed('/login/'),
    _prefixed('/logout/'),
    _prefixed('/api/token/'),
    _prefixed('/api/token/refresh/'),
    '/admin/login/',
)


def _is_public_path(path):
    return (path in PUBLIC_URLS) or any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthRequiredMiddleware:
    """Redirect unauthenticated users to the login page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        is_public_path = _is_public_path(path)
        if not is_public_path:
            if not request.session.get('access_token'):
                return redirect('login')
        response = self.get_response(request)

        if (
            getattr(response, 'status_code', None) == 403
            and request.method == 'GET'
            and request.session.get('access_token')
            and not path.startswith(_prefixed('/api/'))
        ):
            try:
                from core.views import _default_redirect_response

                fallback_response = _default_redirect_response(request)
                current_path = path.rstrip('/') or '/'
                fallback_path = str(getattr(fallback_response, 'url', '') or '').rstrip('/') or '/'
                if fallback_path and current_path != fallback_path:
                    return fallback_response
            except Exception:
                return response

        return response

class DemoModeMiddleware:
    """Prevent write operations when DEMO_MODE is enabled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not bool(getattr(settings, 'DEMO_MODE', False)):
            return self.get_response(request)

        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return self.get_response(request)

        path = request.path or ''
        if path in DEMO_ALLOWED_PATHS:
            return self.get_response(request)

        message = 'Demo mode is enabled. This action is disabled on the live demo server.'

        if path.startswith(_prefixed('/api/')):
            return JsonResponse({'detail': message}, status=403)

        if '_messages' not in request.session:
            request.session['_messages'] = []
        request.session['_messages'].append({'message': message, 'level': 'warning'})
        referer = request.META.get('HTTP_REFERER') or '/'
        return redirect(referer)
