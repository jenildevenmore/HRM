import json

import jwt
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .utils import (
    LicenseActivationError,
    activate_license,
    get_server_fingerprint,
    load_license_state,
    validate_stored_license,
)


def _extract_license_key(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            payload = {}
        return str(payload.get("license_key", "")).strip()
    return str(request.POST.get("license_key", "")).strip()


def _is_json_request(request):
    app_prefix = "/" + str(getattr(settings, "APP_URL_PREFIX", "") or "").strip().strip("/")
    api_prefix = f"{app_prefix}/api/" if app_prefix != "/" else "/api/"
    return (
        request.path.startswith(api_prefix)
        or "application/json" in request.headers.get("Accept", "")
        or "application/json" in (request.content_type or "")
    )


def _activation_form_html(request, error_message=""):
    activation_api = reverse("license_activate_api")
    status_api = reverse("license_status_api")
    fingerprint = get_server_fingerprint()
    error_block = f"<p style='color:#b42318;'>{error_message}</p>" if error_message else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>License Activation</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family:Arial,sans-serif;max-width:640px;margin:48px auto;padding:0 16px;">
  <h1>Activate License</h1>
  <p>This client installation is not activated.</p>
  <p><strong>Server fingerprint:</strong> <code>{fingerprint}</code></p>
  {error_block}
  <form method="post" action="">
    <label for="license_key">License key</label><br>
    <input id="license_key" name="license_key" type="text" style="width:100%;max-width:420px;padding:8px;margin:8px 0 16px;" required>
    <br>
    <button type="submit" style="padding:10px 16px;">Activate</button>
  </form>
  <p>API endpoint: <code>{activation_api}</code></p>
  <p>Status endpoint: <code>{status_api}</code></p>
</body>
</html>"""


@csrf_exempt
@require_http_methods(["GET", "POST"])
def license_activation_view(request):
    if request.method == "GET":
        return HttpResponse(_activation_form_html(request), content_type="text/html")

    license_key = _extract_license_key(request)
    if not license_key:
        message = "license_key is required."
        if _is_json_request(request):
            return JsonResponse({"success": False, "detail": message}, status=400)
        return HttpResponse(_activation_form_html(request, error_message=message), status=400)

    try:
        activation_result = activate_license(license_key)
    except jwt.ExpiredSignatureError:
        message = "Received an expired token from the license server."
        if _is_json_request(request):
            return JsonResponse({"success": False, "detail": message}, status=400)
        return HttpResponse(_activation_form_html(request, error_message=message), status=400)
    except jwt.InvalidTokenError:
        message = "Received an invalid token from the license server."
        if _is_json_request(request):
            return JsonResponse({"success": False, "detail": message}, status=400)
        return HttpResponse(_activation_form_html(request, error_message=message), status=400)
    except LicenseActivationError as exc:
        if _is_json_request(request):
            return JsonResponse({"success": False, "detail": str(exc)}, status=502)
        return HttpResponse(_activation_form_html(request, error_message=str(exc)), status=502)

    if _is_json_request(request):
        return JsonResponse(
            {
                "success": True,
                "detail": "License activated successfully.",
                "fingerprint": activation_result["fingerprint"],
                "expires_at": activation_result["payload"].get("exp"),
            },
            status=200,
        )

    return HttpResponse(
        f"<html><body><p>License activated successfully.</p><p><a href='{reverse('dashboard')}'>Continue</a></p></body></html>",
        content_type="text/html",
    )


@csrf_exempt
@require_http_methods(["POST"])
def license_activate_api(request):
    return license_activation_view(request)


@require_http_methods(["GET"])
def license_status_api(request):
    result = validate_stored_license(allow_remote_revalidation=True)
    try:
        state = load_license_state()
    except Exception:
        state = {}
    return JsonResponse(
        {
            "valid": result.valid,
            "reason": result.reason,
            "fingerprint": get_server_fingerprint(),
            "last_validated_at": state.get("last_validated_at"),
            "last_activation_at": state.get("last_activation_at"),
        },
        status=200 if result.valid else result.status_code,
    )
