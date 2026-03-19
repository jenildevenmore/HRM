import hashlib
import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import requests
from django.conf import settings
from django.core import signing


class LicenseError(Exception):
    pass


class LicenseActivationError(LicenseError):
    pass


class LicenseStorageError(LicenseError):
    pass


@dataclass
class LicenseValidationResult:
    valid: bool
    reason: str = ""
    payload: dict | None = None
    fingerprint: str | None = None
    token: str | None = None
    should_revalidate: bool = False
    status_code: int = 200


def _utcnow():
    return datetime.now(timezone.utc)


def _license_storage_path():
    raw_path = str(getattr(settings, "LICENSE_STORAGE_PATH", "") or "").strip()
    if raw_path:
        return Path(raw_path)
    return Path(settings.BASE_DIR) / ".license_token"


def _storage_signer():
    return signing.TimestampSigner(salt="client-license-token")


def _serialize_state(state):
    payload = dict(state or {})
    return _storage_signer().sign_object(payload)


def _deserialize_state(raw_value):
    return _storage_signer().unsign_object(raw_value)


def _write_secure_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_license_state():
    storage_path = _license_storage_path()
    if not storage_path.exists():
        return {}

    try:
        raw_value = storage_path.read_text(encoding="utf-8").strip()
        if not raw_value:
            return {}
        return _deserialize_state(raw_value)
    except (OSError, signing.BadSignature) as exc:
        raise LicenseStorageError("Stored license token is unreadable or has been tampered with.") from exc


def save_license_state(state):
    serialized = _serialize_state(state)
    _write_secure_file(_license_storage_path(), serialized)


def get_token():
    state = load_license_state()
    return str(state.get("token", "")).strip() or None


def save_token(token, license_key=None, extra=None):
    token = str(token or "").strip()
    if not token:
        raise LicenseStorageError("Cannot save an empty license token.")

    state = load_license_state()
    state.update(extra or {})
    state["token"] = token
    if license_key:
        state["license_key"] = str(license_key).strip()
    state["updated_at"] = _utcnow().isoformat()
    save_license_state(state)


def clear_token():
    storage_path = _license_storage_path()
    if storage_path.exists():
        storage_path.unlink()


def get_server_fingerprint():
    hostname = socket.gethostname().strip().lower()
    mac_address = f"{uuid.getnode():012x}"
    raw_value = f"{hostname}:{mac_address}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _jwt_key():
    public_key = str(getattr(settings, "LICENSE_JWT_PUBLIC_KEY", "") or "").strip()
    if public_key:
        return public_key
    return str(getattr(settings, "LICENSE_JWT_SECRET_KEY", settings.SECRET_KEY) or "").strip()


def _jwt_decode_options():
    options = {"require": ["exp"]}
    audience = str(getattr(settings, "LICENSE_JWT_AUDIENCE", "") or "").strip()
    issuer = str(getattr(settings, "LICENSE_JWT_ISSUER", "") or "").strip()
    kwargs = {
        "key": _jwt_key(),
        "algorithms": list(getattr(settings, "LICENSE_JWT_ALGORITHMS", ["HS256"])),
        "options": options,
    }
    if audience:
        kwargs["audience"] = audience
    if issuer:
        kwargs["issuer"] = issuer
    return kwargs


def decode_license_token(token):
    token = str(token or "").strip()
    if not token:
        raise jwt.InvalidTokenError("Missing license token.")
    return jwt.decode(token, **_jwt_decode_options())


def _fingerprint_from_payload(payload):
    return (
        payload.get("fingerprint")
        or payload.get("server_fingerprint")
        or payload.get("device_fingerprint")
        or ""
    )


def _dt_from_iso(raw_value):
    raw_value = str(raw_value or "").strip()
    if not raw_value:
        return None
    try:
        normalized = raw_value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _should_revalidate(state):
    interval_seconds = int(getattr(settings, "LICENSE_REVALIDATE_INTERVAL_SECONDS", 14400))
    if interval_seconds <= 0:
        return False
    last_checked_at = _dt_from_iso(state.get("last_validated_at"))
    if last_checked_at is None:
        return True
    return _utcnow() - last_checked_at >= timedelta(seconds=interval_seconds)


def _admin_request(url, payload, timeout=None):
    if not url:
        raise LicenseActivationError("License server URL is not configured.")
    try:
        response = requests.post(
            url,
            json=payload,
            timeout=timeout or int(getattr(settings, "LICENSE_API_TIMEOUT", 10)),
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise LicenseActivationError("License server request failed.") from exc
    except ValueError as exc:
        raise LicenseActivationError("License server returned a non-JSON response.") from exc


def activate_license(license_key):
    license_key = str(license_key or "").strip()
    if not license_key:
        raise LicenseActivationError("license_key is required.")

    fingerprint = get_server_fingerprint()
    payload = {
        "license_key": license_key,
        "fingerprint": fingerprint,
    }
    response_data = _admin_request(settings.LICENSE_SERVER_ACTIVATION_URL, payload)
    token = (
        response_data.get("token")
        or response_data.get("jwt")
        or response_data.get("access_token")
    )
    if not token:
        raise LicenseActivationError("License server response did not include a JWT token.")

    decoded = decode_license_token(token)
    expected_fingerprint = str(_fingerprint_from_payload(decoded)).strip()
    if not expected_fingerprint:
        raise LicenseActivationError("License token is missing a fingerprint claim.")
    if expected_fingerprint != fingerprint:
        raise LicenseActivationError("License token fingerprint does not match this server.")

    save_token(
        token,
        license_key=license_key,
        extra={
            "last_validated_at": _utcnow().isoformat(),
            "last_activation_at": _utcnow().isoformat(),
        },
    )
    return {
        "token": token,
        "payload": decoded,
        "fingerprint": fingerprint,
    }


def revalidate_with_admin_server(force=False):
    state = load_license_state()
    token = str(state.get("token", "")).strip()
    if not token:
        return LicenseValidationResult(valid=False, reason="missing_token", status_code=403)

    if not force and not _should_revalidate(state):
        try:
            payload = decode_license_token(token)
            return LicenseValidationResult(
                valid=True,
                reason="local_validation_ok",
                payload=payload,
                fingerprint=get_server_fingerprint(),
                token=token,
                should_revalidate=False,
            )
        except jwt.PyJWTError:
            pass

    revalidation_url = str(getattr(settings, "LICENSE_SERVER_REVALIDATION_URL", "") or "").strip()
    if not revalidation_url:
        try:
            payload = decode_license_token(token)
            return LicenseValidationResult(
                valid=True,
                reason="revalidation_not_configured",
                payload=payload,
                fingerprint=get_server_fingerprint(),
                token=token,
                should_revalidate=False,
            )
        except jwt.PyJWTError as exc:
            return LicenseValidationResult(valid=False, reason=exc.__class__.__name__.lower(), status_code=403)

    fingerprint = get_server_fingerprint()
    payload = {
        "token": token,
        "fingerprint": fingerprint,
        "license_key": state.get("license_key", ""),
    }
    try:
        response_data = _admin_request(revalidation_url, payload)
    except LicenseActivationError:
        grace_seconds = int(getattr(settings, "LICENSE_SERVER_GRACE_PERIOD_SECONDS", 86400))
        last_checked_at = _dt_from_iso(state.get("last_validated_at"))
        within_grace = bool(last_checked_at and (_utcnow() - last_checked_at <= timedelta(seconds=grace_seconds)))
        if within_grace:
            try:
                decoded = decode_license_token(token)
                return LicenseValidationResult(
                    valid=True,
                    reason="grace_period_active",
                    payload=decoded,
                    fingerprint=fingerprint,
                    token=token,
                    should_revalidate=True,
                )
            except jwt.PyJWTError as exc:
                return LicenseValidationResult(valid=False, reason=exc.__class__.__name__.lower(), status_code=403)
        return LicenseValidationResult(valid=False, reason="admin_server_unreachable", status_code=503)

    refreshed_token = (
        response_data.get("token")
        or response_data.get("jwt")
        or response_data.get("access_token")
        or token
    )
    try:
        decoded = decode_license_token(refreshed_token)
    except jwt.PyJWTError as exc:
        return LicenseValidationResult(valid=False, reason=exc.__class__.__name__.lower(), status_code=403)

    save_token(
        refreshed_token,
        license_key=state.get("license_key"),
        extra={"last_validated_at": _utcnow().isoformat()},
    )
    return LicenseValidationResult(
        valid=True,
        reason="revalidated",
        payload=decoded,
        fingerprint=fingerprint,
        token=refreshed_token,
        should_revalidate=False,
    )


def validate_stored_license(allow_remote_revalidation=True):
    try:
        state = load_license_state()
    except LicenseStorageError:
        return LicenseValidationResult(valid=False, reason="invalid_storage", status_code=403)

    token = str(state.get("token", "")).strip()
    if not token:
        return LicenseValidationResult(valid=False, reason="missing_token", status_code=403)

    fingerprint = get_server_fingerprint()
    try:
        payload = decode_license_token(token)
    except jwt.ExpiredSignatureError:
        return LicenseValidationResult(valid=False, reason="token_expired", token=token, status_code=403)
    except jwt.InvalidTokenError:
        return LicenseValidationResult(valid=False, reason="invalid_token", token=token, status_code=403)

    token_fingerprint = str(_fingerprint_from_payload(payload)).strip()
    if not token_fingerprint:
        return LicenseValidationResult(
            valid=False,
            reason="missing_fingerprint_claim",
            payload=payload,
            fingerprint=fingerprint,
            token=token,
            status_code=403,
        )
    if token_fingerprint != fingerprint:
        return LicenseValidationResult(
            valid=False,
            reason="fingerprint_mismatch",
            payload=payload,
            fingerprint=fingerprint,
            token=token,
            status_code=403,
        )

    if allow_remote_revalidation and _should_revalidate(state):
        remote_result = revalidate_with_admin_server(force=True)
        if not remote_result.valid:
            return remote_result
        return remote_result

    return LicenseValidationResult(
        valid=True,
        reason="valid",
        payload=payload,
        fingerprint=fingerprint,
        token=token,
        should_revalidate=False,
    )
