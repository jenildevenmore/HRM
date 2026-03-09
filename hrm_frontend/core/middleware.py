from django.shortcuts import redirect

# URLs that do NOT require authentication
PUBLIC_URLS = ['/login/', '/logout/', '/reset-password/']


class AuthRequiredMiddleware:
    """Redirect unauthenticated users to the login page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path not in PUBLIC_URLS:
            if not request.session.get('access_token'):
                return redirect('login')
        return self.get_response(request)
