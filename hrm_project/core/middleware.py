from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

# URLs that do NOT require authentication
PUBLIC_URLS = ['/login/', '/logout/', '/forgot-password/', '/reset-password/']
PUBLIC_PREFIXES = (
    '/api/',
    '/admin/',
    '/static/',
    '/media/',
    '/document-upload/',
    '/favicon.ico',
)
DEMO_ALLOWED_PATHS = (
    '/login/',
    '/logout/',
    '/api/token/',
    '/api/token/refresh/',
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
            role = request.session.get('role')
            app_settings = request.session.get('app_settings')
            onboarding = app_settings.get('onboarding') if isinstance(app_settings, dict) else {}
            org_setup_done = bool(onboarding.get('org_setup_completed')) if isinstance(onboarding, dict) else False
            if (
                role == 'admin'
                and not org_setup_done
                and not path.startswith('/onboarding/setup-org/')
                and not path.startswith('/logout/')
            ):
                return redirect('org_setup_onboarding')
        return self.get_response(request)

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

        if path.startswith('/api/'):
            return JsonResponse({'detail': message}, status=403)

        if '_messages' not in request.session:
            request.session['_messages'] = []
        request.session['_messages'].append({'message': message, 'level': 'warning'})
        referer = request.META.get('HTTP_REFERER') or '/'
        return redirect(referer)
