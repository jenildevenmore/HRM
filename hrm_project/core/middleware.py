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


class AuthRequiredMiddleware:
    """Redirect unauthenticated users to the login page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        is_public_path = (path in PUBLIC_URLS) or any(path.startswith(p) for p in PUBLIC_PREFIXES)
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
