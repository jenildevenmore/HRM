from django.shortcuts import redirect

# URLs that do NOT require authentication
PUBLIC_URLS = ['/login/', '/logout/', '/reset-password/']
PUBLIC_PREFIXES = (
    '/api/',
    '/admin/',
    '/static/',
    '/media/',
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
        return self.get_response(request)
