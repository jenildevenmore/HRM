from .utils import (
    LicenseValidationResult,
    activate_license,
    decode_license_token,
    get_server_fingerprint,
    get_token,
    save_token,
    validate_stored_license,
)


def ensure_license_key():
    result = validate_stored_license(allow_remote_revalidation=False)
    if result.valid:
        return result
    raise RuntimeError(f"Project startup blocked. License validation failed: {result.reason}")
