from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .utils import validate_stored_license


def _prefixed(path):
    app_prefix = str(getattr(settings, "APP_URL_PREFIX", "") or "").strip().strip("/")
    clean = "/" + str(path or "").strip().lstrip("/")
    if not app_prefix:
        return clean
    prefix = f"/{app_prefix}"
    if clean == prefix or clean.startswith(f"{prefix}/"):
        return clean
    return f"{prefix}{clean}"


PUBLIC_LICENSE_PATHS = {
    _prefixed("/license/activate/"),
    _prefixed("/api/license/activate/"),
    _prefixed("/api/license/status/"),
    "/favicon.ico",
}

PUBLIC_LICENSE_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",
)


class LicenseValidationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or "/"
        if path in PUBLIC_LICENSE_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_LICENSE_PREFIXES):
            return self.get_response(request)

        result = validate_stored_license(allow_remote_revalidation=True)
        request.license_validation = result
        if result.valid:
            return self.get_response(request)

        is_api_request = path.startswith(_prefixed("/api/")) or "application/json" in request.headers.get("Accept", "")
        detail = {
            "detail": "License validation failed.",
            "reason": result.reason,
            "activation_url": _prefixed("/license/activate/"),
            "status_url": _prefixed("/api/license/status/"),
        }
        if is_api_request:
            return JsonResponse(detail, status=result.status_code or 403)

        activation_url = reverse("license_activation")
        return redirect(f"{activation_url}?reason={result.reason}")
