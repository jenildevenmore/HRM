import requests
import json
import datetime
import calendar
import csv
import re
import os
import uuid
import io
from urllib.parse import urlparse
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone
from django.test import Client as DjangoTestClient
from core.mailers import send_branded_email

from core.forms import (
    LoginForm,
    EmployeeForm,
    CustomFieldForm,
    ClientForm,
    DynamicModelForm,
    DynamicFieldForm,
    DynamicRecordForm,
)

API = settings.BACKEND_API_URL
API_TIMEOUT = int(getattr(settings, 'API_TIMEOUT', 10))

ADDON_KEYS = {
    'custom_fields',
    'dynamic_models',
    'attendance',
    'attendance_location',
    'attendance_selfie_location',
    'leave_management',
    'holidays',
    'payroll',
    'activity_logs',
    'settings',
    'policy',
    'documents',
    'import_export',
    'role_management',
    'shift_management',
    'bank_management',
}
ADDON_OPTIONS = [
    ('custom_fields', 'Custom Fields'),
    ('dynamic_models', 'Dynamic Models'),
    ('attendance', 'Attendance'),
    ('attendance_location', 'Attendance + Location'),
    ('attendance_selfie_location', 'Attendance + Selfie + Location'),
    ('leave_management', 'Leave Management'),
    ('holidays', 'Holidays'),
    ('payroll', 'Payroll'),
    ('activity_logs', 'Activity Logs'),
    ('settings', 'Settings'),
    ('policy', 'Policy'),
    ('documents', 'Documents'),
    ('import_export', 'Import / Export'),
    ('role_management', 'Role Management'),
    ('shift_management', 'Shift Management'),
    ('bank_management', 'Bank Management'),
]

STATIC_PERMISSION_KEYS = {
    'employees.view', 'employees.create', 'employees.edit', 'employees.delete',
    'attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete',
    'leaves.view', 'leaves.create', 'leaves.edit', 'leaves.delete', 'leaves.approve',
    'holidays.view', 'holidays.create', 'holidays.edit', 'holidays.delete',
    'shifts.view', 'shifts.create', 'shifts.edit', 'shifts.delete',
    'bank.view', 'bank.create', 'bank.edit', 'bank.delete',
    'policy.view', 'policy.create', 'policy.edit', 'policy.delete',
    'documents.view', 'documents.create', 'documents.edit', 'documents.delete',
    'import_export.view', 'import_export.import', 'import_export.export',
    'custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete',
    'dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete',
    'activity_logs.view',
}

LEGACY_PERMISSION_MAP = {
    'employees': ['employees.view', 'employees.create', 'employees.edit', 'employees.delete'],
    'attendance': ['attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete'],
    'leaves': ['leaves.view', 'leaves.create', 'leaves.edit', 'leaves.delete', 'leaves.approve'],
    'holidays': ['holidays.view', 'holidays.create', 'holidays.edit', 'holidays.delete'],
    'shifts': ['shifts.view', 'shifts.create', 'shifts.edit', 'shifts.delete'],
    'bank': ['bank.view', 'bank.create', 'bank.edit', 'bank.delete'],
    'policy': ['policy.view', 'policy.create', 'policy.edit', 'policy.delete'],
    'documents': ['documents.view', 'documents.create', 'documents.edit', 'documents.delete'],
    'import_export': ['import_export.view', 'import_export.import', 'import_export.export'],
    'custom_fields': ['custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete'],
    'dynamic_models': ['dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete'],
}
ADDON_VIEW_PERMISSION_MAP = {
    'custom_fields': 'custom_fields.view',
    'dynamic_models': 'dynamic_models.view',
    'attendance': 'attendance.view',
    'leave_management': 'leaves.view',
    'holidays': 'holidays.view',
    'shift_management': 'shifts.view',
    'bank_management': 'bank.view',
    'payroll': 'payroll.view',
    'activity_logs': 'activity_logs.view',
    'policy': 'policy.view',
    'documents': 'documents.view',
    'import_export': 'import_export.view',
}

SIDEBAR_LOGO_MODULES = [
    {'key': 'dashboard', 'label': 'Dashboard'},
    {'key': 'employees', 'label': 'Employees'},
    {'key': 'attendance', 'label': 'Attendance'},
    {'key': 'leaves', 'label': 'Leaves'},
    {'key': 'payroll', 'label': 'Payroll'},
    {'key': 'import_export', 'label': 'Import/Export'},
    {'key': 'activity_logs', 'label': 'Activity Logs'},
    {'key': 'holidays', 'label': 'Holidays'},
    {'key': 'shifts', 'label': 'Shifts'},
    {'key': 'bank', 'label': 'Bank'},
    {'key': 'policy', 'label': 'Policy'},
    {'key': 'documents', 'label': 'Documents'},
    {'key': 'clients', 'label': 'Clients'},
    {'key': 'custom_fields', 'label': 'Custom Fields'},
    {'key': 'dynamic_models', 'label': 'Dynamic Models'},
    {'key': 'roles', 'label': 'Roles'},
    {'key': 'settings', 'label': 'Settings'},
]


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _auth_headers(request):
    """Return Authorization header using the token stored in the session."""
    token = request.session.get('access_token', '')
    return {'Authorization': f'Bearer {token}'}


class _InternalAPIResponse:
    def __init__(self, django_response):
        self.status_code = django_response.status_code
        self._content = django_response.content or b''

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._content.decode('utf-8', errors='replace')

    def json(self):
        if not self._content:
            return {}
        return json.loads(self._content.decode('utf-8'))


def _use_internal_api():
    # For single-project deployment (UI + API in same Django), avoid self-HTTP calls.
    return str(getattr(settings, 'USE_INTERNAL_API', 'true')).strip().lower() in ('1', 'true', 'yes', 'on')


def _to_internal_path(path):
    raw = str(path or '').strip()
    if raw.startswith('http://') or raw.startswith('https://'):
        parsed = urlparse(raw)
        suffix = f'?{parsed.query}' if parsed.query else ''
        return f'{parsed.path}{suffix}'
    if not raw.startswith('/'):
        return f'/{raw}'
    return raw


def _internal_api_request(method, path, headers=None, params=None, data=None, host=None):
    client = DjangoTestClient()
    request_headers = {}
    for key, value in (headers or {}).items():
        normalized = str(key).strip().upper().replace('-', '_')
        if normalized == 'CONTENT_TYPE':
            continue
        request_headers[f'HTTP_{normalized}'] = value
    if host:
        request_headers['HTTP_HOST'] = host

    internal_path = _to_internal_path(path)
    method_upper = str(method).upper()

    if method_upper == 'GET':
        resp = client.get(internal_path, data=params or None, **request_headers)
    elif method_upper == 'POST':
        resp = client.post(
            internal_path,
            data=json.dumps(data or {}),
            content_type='application/json',
            **request_headers,
        )
    elif method_upper == 'PUT':
        resp = client.put(
            internal_path,
            data=json.dumps(data or {}),
            content_type='application/json',
            **request_headers,
        )
    elif method_upper == 'PATCH':
        resp = client.patch(
            internal_path,
            data=json.dumps(data or {}),
            content_type='application/json',
            **request_headers,
        )
    elif method_upper == 'DELETE':
        resp = client.delete(internal_path, data=params or None, **request_headers)
    else:
        raise ValueError(f'Unsupported method: {method}')

    return _InternalAPIResponse(resp)


def _external_api_request(method, path, headers=None, params=None, data=None):
    url = f'{API.rstrip("/")}{_to_internal_path(path)}'
    return requests.request(
        method=method,
        url=url,
        headers=headers or {},
        params=params,
        json=data,
        timeout=API_TIMEOUT,
    )


def _api_request(method, path, headers=None, params=None, data=None, host=None):
    if _use_internal_api():
        return _internal_api_request(method, path, headers=headers, params=params, data=data, host=host)
    return _external_api_request(method, path, headers=headers, params=params, data=data)


def _api_get(request, path, params=None):
    host = request.get_host() if request else None
    return _api_request('GET', path, headers=_auth_headers(request), params=params, host=host)


def _api_post(request, path, data):
    host = request.get_host() if request else None
    return _api_request('POST', path, headers=_auth_headers(request), data=data, host=host)


def _api_put(request, path, data):
    host = request.get_host() if request else None
    return _api_request('PUT', path, headers=_auth_headers(request), data=data, host=host)


def _api_delete(request, path):
    host = request.get_host() if request else None
    return _api_request('DELETE', path, headers=_auth_headers(request), host=host)


def _serialize_data(data):
    """Convert date/datetime objects to ISO format strings for JSON serialization."""
    import datetime
    serialized = {}
    for key, value in data.items():
        if isinstance(value, (datetime.date, datetime.datetime)):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _store_uploaded_dynamic_file(uploaded_file, folder='dynamic_uploads'):
    """Store uploaded file in frontend media and return public URL path."""
    ext = os.path.splitext(uploaded_file.name or '')[1].lower()
    base_name = slugify(os.path.splitext(uploaded_file.name or 'file')[0]) or 'file'
    stamp = datetime.datetime.now().strftime('%Y/%m')
    rel_path = f'{folder}/{stamp}/{base_name}-{uuid.uuid4().hex[:10]}{ext}'
    saved_path = default_storage.save(rel_path, uploaded_file)
    return default_storage.url(saved_path)


def _parse_time_to_datetime(value):
    """Parse time/datetime strings into datetime for duration calculations."""
    if not value:
        return None

    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, datetime.time):
        return datetime.datetime.combine(timezone.localdate(), value)

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            parsed_time = datetime.datetime.strptime(raw, fmt).time()
            return datetime.datetime.combine(timezone.localdate(), parsed_time)
        except ValueError:
            continue

    # Support full ISO datetime values as fallback.
    try:
        iso_raw = raw.replace('Z', '+00:00')
        parsed_dt = datetime.datetime.fromisoformat(iso_raw)
        if parsed_dt.tzinfo is not None:
            parsed_dt = parsed_dt.astimezone().replace(tzinfo=None)
        return parsed_dt
    except ValueError:
        return None


def _format_duration(delta):
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def _attendance_total_time(data, end_override=None):
    """Return HH:MM:SS between check_in and check_out (or override end)."""
    check_in_dt = _parse_time_to_datetime(data.get('check_in'))
    check_out_value = end_override if end_override is not None else data.get('check_out')
    check_out_dt = _parse_time_to_datetime(check_out_value)

    if not check_in_dt or not check_out_dt:
        return ''

    if check_out_dt < check_in_dt:
        check_out_dt += datetime.timedelta(days=1)
    return _format_duration(check_out_dt - check_in_dt)


def _build_attendance_calendar(employee, attendance_records, year, month):
    month_matrix = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    today = timezone.localdate()
    joining_date_raw = employee.get('joining_date')
    joining_date = None
    if joining_date_raw:
        try:
            joining_date = datetime.date.fromisoformat(str(joining_date_raw))
        except ValueError:
            joining_date = None

    record_map = {}
    present_days = 0
    absent_days = 0
    total_seconds = 0

    for rec in attendance_records:
        data = rec.get('data', {})
        raw_date = data.get('attendance_date')
        if not raw_date:
            continue
        try:
            att_date = datetime.date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        record_map[att_date] = rec

    weeks = []
    for week in month_matrix:
        week_cells = []
        for day in week:
            in_month = day.month == month
            record = record_map.get(day)
            data = record.get('data', {}) if record else {}
            total_time = _attendance_total_time(data) if record else ''
            is_future = day > today
            before_joining = bool(joining_date and day < joining_date)

            if record:
                status = str(data.get('status') or 'present').lower()
                if status == 'present':
                    present_days += 1
                elif in_month:
                    absent_days += 1
                if total_time:
                    parsed = _parse_time_to_datetime(total_time)
                    if parsed:
                        total_seconds += parsed.hour * 3600 + parsed.minute * 60 + parsed.second
            elif in_month and not is_future and not before_joining:
                status = 'absent'
                absent_days += 1
            else:
                status = ''

            week_cells.append({
                'date': day,
                'day_number': day.day,
                'in_month': in_month,
                'is_today': day == today,
                'status': status,
                'hours': total_time,
                'check_in': data.get('check_in', ''),
                'check_out': data.get('check_out', ''),
                'before_joining': before_joining,
                'is_future': is_future,
            })
        weeks.append(week_cells)

    month_start = datetime.date(year, month, 1)
    prev_month = (month_start - datetime.timedelta(days=1)).replace(day=1)
    next_month = (month_start + datetime.timedelta(days=32)).replace(day=1)

    return {
        'label': month_start.strftime('%B %Y'),
        'weeks': weeks,
        'present_days': present_days,
        'absent_days': absent_days,
        'worked_hours': _format_duration(datetime.timedelta(seconds=total_seconds)),
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
    }


def _normalize_enabled_addons(addons):
    cleaned = [a for a in (addons or []) if a in ADDON_KEYS]
    normalized = list(dict.fromkeys(cleaned))
    if 'attendance_selfie_location' in normalized and 'attendance_location' not in normalized:
        normalized.append('attendance_location')
    if (
        'attendance_location' in normalized
        or 'attendance_selfie_location' in normalized
    ) and 'attendance' not in normalized:
        normalized.append('attendance')
    return normalized


def _normalize_module_permissions(permissions):
    cleaned = []
    for item in permissions or []:
        key = str(item).strip()
        if not key:
            continue
        if key in LEGACY_PERMISSION_MAP:
            for expanded in LEGACY_PERMISSION_MAP[key]:
                if expanded not in cleaned:
                    cleaned.append(expanded)
            continue
        if key in STATIC_PERMISSION_KEYS or re.fullmatch(r'dynamic_model\.\d+\.(view|create|edit|delete)', key):
            if key not in cleaned:
                cleaned.append(key)
    return cleaned


def _merge_view_permissions_from_addons(module_permissions, enabled_addons):
    merged = list(module_permissions or [])
    addon_set = set(enabled_addons or [])
    for addon_key, permission_key in ADDON_VIEW_PERMISSION_MAP.items():
        if addon_key in addon_set and permission_key not in merged:
            merged.append(permission_key)
    return merged


def _load_client_addons(request, access_token=None, client_id=None):
    target_client_id = client_id or request.session.get('client_id')
    if not target_client_id:
        return []

    headers = _auth_headers(request)
    if access_token:
        headers = {'Authorization': f'Bearer {access_token}'}

    try:
        resp = _api_request('GET', f'/api/clients/{target_client_id}/', headers=headers, host=request.get_host())
        if resp.status_code == 200:
            return _normalize_enabled_addons(resp.json().get('enabled_addons') or [])
    except requests.exceptions.RequestException:
        return []
    return []


def _load_client_app_settings(request, access_token=None, client_id=None):
    target_client_id = client_id or request.session.get('client_id')
    if not target_client_id:
        return {}

    headers = _auth_headers(request)
    if access_token:
        headers = {'Authorization': f'Bearer {access_token}'}

    try:
        resp = _api_request('GET', f'/api/clients/{target_client_id}/', headers=headers, host=request.get_host())
        if resp.status_code == 200:
            payload = resp.json()
            app_settings = payload.get('app_settings')
            return app_settings if isinstance(app_settings, dict) else {}
    except requests.exceptions.RequestException:
        return {}
    return {}


def _load_auto_clockout_alerts(request, limit=8):
    """Load recent auto clock-out attendance events for UI cards."""
    try:
        model_resp = _api_get(request, '/api/dynamic-models/')
        if model_resp.status_code != 200:
            return []
        model_payload = model_resp.json()
        models = model_payload.get('results', model_payload) if isinstance(model_payload, dict) else model_payload
        attendance_model = next((m for m in models if str(m.get('slug', '')).lower() == 'attendance'), None)
        if not attendance_model:
            return []

        employees_resp = _api_get(request, '/api/employees/')
        employee_rows = []
        if employees_resp.status_code == 200:
            employee_payload = employees_resp.json()
            employee_rows = (
                employee_payload.get('results', employee_payload)
                if isinstance(employee_payload, dict) else employee_payload
            )
        employee_map = {str(e.get('id')): e for e in employee_rows}

        records_resp = _api_get(request, '/api/dynamic-records/', params={'dynamic_model': attendance_model.get('id')})
        if records_resp.status_code != 200:
            return []
        records_payload = records_resp.json()
        records = records_payload.get('results', records_payload) if isinstance(records_payload, dict) else records_payload

        session_role = request.session.get('role', 'employee')
        session_employee_role = (request.session.get('employee_role') or '').strip().lower()
        session_employee_id = request.session.get('employee_id')
        is_manager_like = session_role in ('admin', 'superadmin') or session_employee_role in ('manager', 'hr')

        rows = []
        for rec in records:
            data = rec.get('data') or {}
            remarks = str(data.get('remarks') or '')
            if 'Auto clock-out by system' not in remarks:
                continue
            emp_id = str(rec.get('employee'))
            emp = employee_map.get(emp_id, {})

            # For manager/hr employee login, show only their team alerts.
            if session_role == 'employee' and session_employee_role in ('manager', 'hr') and session_employee_id:
                if session_employee_role == 'manager' and str(emp.get('manager') or '') != str(session_employee_id):
                    continue
                if session_employee_role == 'hr' and str(emp.get('hr') or '') != str(session_employee_id):
                    continue
            elif session_role == 'employee' and not is_manager_like and session_employee_id:
                if emp_id != str(session_employee_id):
                    continue

            rows.append({
                'record_id': rec.get('id'),
                'employee_id': rec.get('employee'),
                'employee_name': f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip() or f"Employee #{emp_id}",
                'manager_name': emp.get('manager_name') or '-',
                'hr_name': emp.get('hr_name') or '-',
                'attendance_date': data.get('attendance_date') or '-',
                'check_in': data.get('check_in') or '-',
                'check_out': data.get('check_out') or '-',
            })

        rows.sort(key=lambda x: (str(x.get('attendance_date') or ''), int(x.get('record_id') or 0)), reverse=True)
        return rows[:limit]
    except requests.exceptions.ConnectionError:
        return []


def _get_context(request):
    """Return common context data for all views"""
    role = request.session.get('role', 'employee')
    module_permissions = _normalize_module_permissions(request.session.get('module_permissions', []))
    request.session['module_permissions'] = module_permissions
    enabled_addons = _normalize_enabled_addons(request.session.get('enabled_addons', []))
    request.session['enabled_addons'] = enabled_addons
    if role == 'superadmin':
        enabled_addons = sorted(ADDON_KEYS)
        request.session['enabled_addons'] = enabled_addons
        module_permissions = sorted(STATIC_PERMISSION_KEYS)
        request.session['module_permissions'] = module_permissions
        request.session.modified = True
    elif role == 'admin':
        module_permissions = sorted(STATIC_PERMISSION_KEYS)
        request.session['module_permissions'] = module_permissions
        enabled_addons = _load_client_addons(request)
        request.session['enabled_addons'] = enabled_addons
        request.session.modified = True
    elif (
        request.session.get('access_token')
        and request.session.get('client_id')
        and not enabled_addons
    ):
        enabled_addons = _load_client_addons(request)
        request.session['enabled_addons'] = enabled_addons
        request.session.modified = True

    app_settings = request.session.get('app_settings', {})
    if not isinstance(app_settings, dict):
        app_settings = {}
    if request.session.get('access_token') and request.session.get('client_id') and not app_settings:
        app_settings = _load_client_app_settings(request)
        request.session['app_settings'] = app_settings
        request.session.modified = True

    if role not in ('superadmin', 'admin'):
        module_permissions = _merge_view_permissions_from_addons(module_permissions, enabled_addons)
        request.session['module_permissions'] = module_permissions
        request.session.modified = True

    nav_dynamic_models = []
    can_view_dynamic_models = (
        role == 'superadmin'
        or 'dynamic_models.view' in module_permissions
        or 'attendance.view' in module_permissions
        or any(p.startswith('dynamic_model.') and p.endswith('.view') for p in module_permissions)
    )
    if request.session.get('access_token') and can_view_dynamic_models and (
        role == 'superadmin'
        or 'dynamic_models' in enabled_addons
        or 'attendance' in enabled_addons
    ):
        try:
            nav_resp = _api_get(request, '/api/dynamic-models/')
            if nav_resp.status_code == 200:
                nav_data = nav_resp.json()
                nav_dynamic_models = (
                    nav_data.get('results', nav_data)
                    if isinstance(nav_data, dict) else nav_data
                )
                filtered = []
                for m in nav_dynamic_models:
                    is_attendance = str(m.get('slug', '')).lower() == 'attendance'
                    if is_attendance:
                        if 'attendance' in enabled_addons and (
                            role in ('superadmin', 'admin') or 'attendance.view' in module_permissions
                        ):
                            filtered.append(m)
                    elif 'dynamic_models' in enabled_addons and (
                        role in ('superadmin', 'admin')
                        or f"dynamic_model.{m.get('id')}.view" in module_permissions
                    ):
                        filtered.append(m)
                nav_dynamic_models = filtered
        except requests.exceptions.RequestException:
            nav_dynamic_models = []

    return {
        'username': request.session.get('username', ''),
        'role': role,
        'module_permissions': module_permissions,
        'enabled_addons': enabled_addons,
        'app_settings': app_settings,
        'nav_dynamic_models': nav_dynamic_models,
    }


def _has_addon(request, addon_key):
    role = request.session.get('role', 'employee')
    if role == 'superadmin':
        return True
    enabled_addons = set(_normalize_enabled_addons(request.session.get('enabled_addons', [])))
    return addon_key in enabled_addons


def _has_module_permission(request, permission_key):
    role = request.session.get('role', 'employee')
    if role in ('superadmin', 'admin'):
        return True
    permissions = set(_normalize_module_permissions(request.session.get('module_permissions', [])))
    return permission_key in permissions


def _has_any_module_permission(request, permission_keys):
    return any(_has_module_permission(request, key) for key in (permission_keys or []))


def _require_module_permission(request, permission_key):
    if _has_module_permission(request, permission_key):
        return None
    _flash(request, 'You do not have permission to access this module.', 'error')
    return redirect('dashboard')


def _require_addon(request, addon_key):
    if _has_addon(request, addon_key):
        return None
    _flash(request, 'This feature is disabled for your client. Ask superadmin to enable it.', 'error')
    return redirect('dashboard')


def _attendance_feature_flags(request):
    selfie_with_location = _has_addon(request, 'attendance_selfie_location')
    location_required = selfie_with_location or _has_addon(request, 'attendance_location')
    return {
        'attendance_location_required': location_required,
        'attendance_selfie_required': selfie_with_location,
    }


def _get_sidebar_logo_modules(request):
    modules = list(SIDEBAR_LOGO_MODULES)
    try:
        resp = _api_get(request, '/api/dynamic-models/')
        if resp.status_code == 200:
            payload = resp.json()
            rows = payload.get('results', payload) if isinstance(payload, dict) else payload
            for row in rows or []:
                model_id = row.get('id')
                if model_id is None:
                    continue
                slug = str(row.get('slug') or '').strip().lower()
                if slug == 'attendance':
                    continue
                modules.append({
                    'key': f'dynamic_model_{model_id}',
                    'label': str(row.get('name') or f'Dynamic Model {model_id}').strip(),
                })
    except requests.exceptions.ConnectionError:
        pass
    return modules


def _flash(request, message, level='success'):
    """Add a flash message to the session."""
    if '_messages' not in request.session:
        request.session['_messages'] = []
    request.session['_messages'].append({'message': message, 'level': level})
    request.session.modified = True


def _pdf_escape_text(value):
    raw = str(value or '')
    return raw.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _build_simple_text_pdf(lines):
    safe_lines = [str(line or '').strip() for line in (lines or []) if str(line or '').strip()]
    if not safe_lines:
        safe_lines = ['Offer Letter']

    content_parts = ['BT', '/F1 11 Tf', '50 790 Td']
    first = True
    for line in safe_lines:
        if not first:
            content_parts.append('0 -16 Td')
        first = False
        content_parts.append(f'({_pdf_escape_text(line)}) Tj')
    content_parts.append('ET')
    stream_data = '\n'.join(content_parts).encode('latin-1', errors='replace')

    objects = [
        b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
        b'2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n',
        b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n',
        b'4 0 obj\n<< /Length ' + str(len(stream_data)).encode('ascii') + b' >>\nstream\n' + stream_data + b'\nendstream\nendobj\n',
        b'5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
    ]

    header = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
    body = b''
    offsets = [0]
    current_offset = len(header)
    for obj in objects:
        offsets.append(current_offset)
        body += obj
        current_offset += len(obj)

    xref_offset = len(header) + len(body)
    xref = b'xref\n0 6\n0000000000 65535 f \n'
    for i in range(1, 6):
        xref += f'{offsets[i]:010d} 00000 n \n'.encode('ascii')

    trailer = b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref_offset).encode('ascii') + b'\n%%EOF'
    return header + body + xref + trailer


def _build_offer_letter_pdf(employee_name, state_name, annual_income, components):
    safe_name = str(employee_name or 'Candidate').strip() or 'Candidate'
    safe_state = str(state_name or 'N/A').strip() or 'N/A'
    annual_income_num = float(annual_income or 0)
    lines = [
        'Offer Letter',
        f'Employee: {safe_name}',
        f'State: {safe_state}',
        f'Annual Income (CTC): INR {annual_income_num:,.2f}',
        '-' * 65,
        'Component                             %           Annual            Monthly',
        '-' * 65,
    ]
    total_pct = 0.0
    total_annual = 0.0
    for comp in components or []:
        name = str(comp.get('name') or '').strip()
        if not name:
            continue
        try:
            pct = float(comp.get('pct') or 0)
        except (TypeError, ValueError):
            pct = 0.0
        annual_amt = (annual_income_num * pct) / 100.0
        monthly_amt = annual_amt / 12.0
        total_pct += pct
        total_annual += annual_amt
        lines.append(f'{name[:28]:<28} {pct:>8.2f}% {annual_amt:>14,.2f} {monthly_amt:>14,.2f}')

    lines.extend([
        '-' * 65,
        f'Total                                {total_pct:>8.2f}% {total_annual:>14,.2f} {total_annual/12.0:>14,.2f}',
        '',
        'This is a system-generated offer letter summary.',
    ])
    return _build_simple_text_pdf(lines)


def _pop_messages(request):
    """Pop and return all flash messages."""
    msgs = request.session.pop('_messages', [])
    request.session.modified = True
    return msgs


def _handle_unauthorized(resp, request):
    """If the backend returns 401, clear session and redirect to login."""
    if resp.status_code == 401:
        request.session.flush()
        return redirect('login')
    return None


def _is_org_setup_pending_from_settings(role, app_settings):
    if role != 'admin':
        return False
    if not isinstance(app_settings, dict):
        return True
    onboarding = app_settings.get('onboarding')
    if not isinstance(onboarding, dict):
        return True
    return not bool(onboarding.get('org_setup_completed'))


def _derive_policy_from_onboarding(app_settings, year=None, month=None):
    if not isinstance(app_settings, dict):
        return None
    onboarding = app_settings.get('onboarding')
    if not isinstance(onboarding, dict):
        return None
    if not onboarding.get('org_setup_completed'):
        return None

    today = timezone.localdate()
    target_year = int(year or today.year)
    target_month = int(month or today.month)
    month_days = calendar.monthrange(target_year, target_month)[1]

    payable_mode = str(onboarding.get('payable_days_mode') or 'calendar_month').strip()

    if payable_mode == 'every_30':
        monthly_working_days = 30
    elif payable_mode == 'every_28':
        monthly_working_days = 28
    elif payable_mode == 'every_26':
        monthly_working_days = 26
    elif payable_mode == 'exclude_weekly_offs':
        sundays = sum(
            1
            for day in range(1, month_days + 1)
            if datetime.date(target_year, target_month, day).weekday() == 6
        )
        monthly_working_days = max(month_days - sundays, 1)
    else:
        monthly_working_days = month_days

    try:
        default_shift_hours = int(onboarding.get('default_shift_hours') or 8)
    except (TypeError, ValueError):
        default_shift_hours = 8
    try:
        default_shift_minutes = int(onboarding.get('default_shift_minutes') or 0)
    except (TypeError, ValueError):
        default_shift_minutes = 0

    default_shift_hours = max(0, min(24, default_shift_hours))
    default_shift_minutes = max(0, min(59, default_shift_minutes))
    standard_hours_per_day = round(default_shift_hours + (default_shift_minutes / 60.0), 2)

    return {
        'monthly_working_days': monthly_working_days,
        'standard_hours_per_day': standard_hours_per_day,
        'salary_basis': 'day',
        'allow_extra_hours_payout': False,
        'allow_extra_days_payout': False,
    }


# ─────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────

def login_view(request):
    if request.session.get('access_token'):
        return redirect('dashboard')

    form = LoginForm()
    error = None
    login_mode = request.GET.get('mode') or request.POST.get('login_mode') or 'client'
    selected_client_id = request.GET.get('client') or request.POST.get('client_id')
    clients = []
    selected_client = None
    clients_load_failed = False

    if login_mode != 'superadmin':
        try:
            clients_resp = _api_request('GET', '/api/clients/public/', host=request.get_host())
            if clients_resp.status_code == 200:
                clients = clients_resp.json()
            else:
                clients_load_failed = True
                try:
                    payload = clients_resp.json()
                    detail = payload.get('detail') if isinstance(payload, dict) else None
                except ValueError:
                    detail = None
                error = detail or f'Failed to load clients from backend (HTTP {clients_resp.status_code}).'
        except requests.exceptions.RequestException:
            clients_load_failed = True
            error = 'Backend API timeout/unreachable while loading clients.'

    if login_mode != 'superadmin' and selected_client_id:
        selected_client = next(
            (c for c in clients if str(c.get('id')) == str(selected_client_id)),
            None
        )
        if not selected_client:
            error = 'Selected client not found.'
            selected_client_id = None

    if request.method == 'POST' and (login_mode == 'superadmin' or selected_client_id):
        form = LoginForm(request.POST)
        if form.is_valid():
            payload = {
                'username': form.cleaned_data['username'],
                'password': form.cleaned_data['password'],
            }
            if login_mode == 'superadmin':
                payload['login_mode'] = 'superadmin'
            else:
                payload['client_id'] = selected_client_id
            try:
                resp = _api_request('POST', '/api/token/', data=payload, host=request.get_host())
                if resp.status_code == 200:
                    data = resp.json()
                    request.session['access_token'] = data['access']
                    request.session['refresh_token'] = data.get('refresh', '')
                    request.session['username'] = form.cleaned_data['username']
                    request.session['client_id'] = data.get('client_id')
                    request.session['role'] = data.get('role', 'employee')
                    request.session['user_id'] = data.get('user_id')
                    request.session['user_email'] = data.get('user_email', '')
                    request.session['employee_id'] = data.get('employee_id')
                    request.session['employee_role'] = data.get('employee_role', '')
                    request.session['module_permissions'] = _normalize_module_permissions(
                        data.get('module_permissions', [])
                    )
                    request.session['enabled_addons'] = _normalize_enabled_addons(
                        data.get('enabled_addons', [])
                    )
                    if data.get('role') == 'superadmin':
                        request.session['enabled_addons'] = sorted(ADDON_KEYS)
                        request.session['module_permissions'] = sorted(STATIC_PERMISSION_KEYS)
                    elif data.get('role') == 'admin':
                        request.session['module_permissions'] = sorted(STATIC_PERMISSION_KEYS)
                    elif not request.session['enabled_addons']:
                        request.session['enabled_addons'] = _load_client_addons(
                            request,
                            access_token=data['access'],
                            client_id=data.get('client_id'),
                        )
                    request.session['app_settings'] = _load_client_app_settings(
                        request,
                        access_token=data['access'],
                        client_id=data.get('client_id'),
                    )
                    if _is_org_setup_pending_from_settings(
                        request.session.get('role'),
                        request.session.get('app_settings'),
                    ):
                        return redirect('org_setup_onboarding')
                    return redirect('dashboard')
                else:
                    error = 'Invalid username or password.'
            except requests.exceptions.RequestException:
                error = 'Backend API timeout/unreachable during login. Please try again.'

    return render(request, 'login.html', {
        'form': form,
        'error': error,
        'clients': clients,
        'selected_client': selected_client,
        'selected_client_id': selected_client_id,
        'clients_load_failed': clients_load_failed,
        'login_mode': login_mode,
    })


def reset_password_view(request):
    uid = (request.GET.get('uid') or request.POST.get('uid') or '').strip()
    token = (request.GET.get('token') or request.POST.get('token') or '').strip()
    error = None
    success = None

    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not uid or not token:
            error = 'Invalid reset link. Please use the link from email.'
        elif not password:
            error = 'Password is required.'
        elif password != confirm_password:
            error = 'Password and confirm password do not match.'
        else:
            try:
                resp = _api_request(
                    'POST',
                    '/api/accounts/password-setup-confirm/',
                    data={'uid': uid, 'token': token, 'new_password': password},
                    host=request.get_host(),
                )
                if resp.status_code == 200:
                    success = 'Password set successfully. You can now login.'
                else:
                    error = '; '.join(_error_list_from_response(resp, 'Failed to set password.'))
            except requests.exceptions.ConnectionError:
                error = 'Backend server unreachable.'

    return render(request, 'reset_password.html', {
        'uid': uid,
        'token': token,
        'error': error,
        'success': success,
    })


def forgot_password_view(request):
    if request.session.get('access_token'):
        return redirect('dashboard')

    error = None
    success = None
    debug_reset_link = ''
    identifier = (request.POST.get('identifier') or '').strip()
    selected_client_id = (request.GET.get('client') or request.POST.get('client_id') or '').strip()
    clients = []
    clients_load_failed = False

    try:
        clients_resp = _api_request('GET', '/api/clients/public/', host=request.get_host())
        if clients_resp.status_code == 200:
            clients = clients_resp.json()
        else:
            clients_load_failed = True
    except requests.exceptions.RequestException:
        clients_load_failed = True

    if request.method == 'POST':
        if not identifier:
            error = 'Email or username is required.'
        else:
            payload = {'identifier': identifier}
            if selected_client_id:
                payload['client_id'] = selected_client_id
            try:
                resp = _api_request(
                    'POST',
                    '/api/accounts/password-reset-request/',
                    data=payload,
                    host=request.get_host(),
                )
                if resp.status_code == 200:
                    data = resp.json() if hasattr(resp, 'json') else {}
                    success = str((data or {}).get('detail') or 'Reset instructions sent if account exists.')
                    debug_reset_link = str((data or {}).get('debug_reset_link') or '')
                else:
                    error = '; '.join(_error_list_from_response(resp, 'Failed to send reset link.'))
            except requests.exceptions.ConnectionError:
                error = 'Backend server unreachable.'

    return render(request, 'forgot_password.html', {
        'error': error,
        'success': success,
        'identifier': identifier,
        'selected_client_id': selected_client_id,
        'clients': clients,
        'clients_load_failed': clients_load_failed,
        'debug_reset_link': debug_reset_link,
    })


def logout_view(request):
    request.session.flush()
    return redirect('login')


# ─────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────

def org_setup_onboarding(request):
    if not request.session.get('access_token'):
        return redirect('login')

    role = request.session.get('role')
    if role != 'admin':
        return redirect('dashboard')

    app_settings = request.session.get('app_settings')
    if not isinstance(app_settings, dict):
        app_settings = {}
    if not _is_org_setup_pending_from_settings(role, app_settings):
        return redirect('dashboard')

    errors = []
    selected_mode = ((app_settings.get('onboarding') or {}).get('payable_days_mode') or 'calendar_month').strip()
    default_hours = int((app_settings.get('onboarding') or {}).get('default_shift_hours') or 8)
    default_minutes = int((app_settings.get('onboarding') or {}).get('default_shift_minutes') or 0)

    if request.method == 'POST':
        selected_mode = (request.POST.get('payable_days_mode') or 'calendar_month').strip()
        try:
            default_hours = int((request.POST.get('default_shift_hours') or '8').strip())
        except (TypeError, ValueError):
            default_hours = 8
        try:
            default_minutes = int((request.POST.get('default_shift_minutes') or '0').strip())
        except (TypeError, ValueError):
            default_minutes = 0

        allowed_modes = {'calendar_month', 'every_30', 'every_28', 'every_26', 'exclude_weekly_offs'}
        if selected_mode not in allowed_modes:
            errors.append('Invalid payable days option selected.')
        if default_hours < 0 or default_hours > 24:
            errors.append('Shift hours must be between 0 and 24.')
        if default_minutes < 0 or default_minutes > 59:
            errors.append('Shift minutes must be between 0 and 59.')

        if not errors:
            onboarding_settings = dict(app_settings.get('onboarding') or {})
            onboarding_settings.update({
                'org_setup_completed': True,
                'payable_days_mode': selected_mode,
                'default_shift_hours': default_hours,
                'default_shift_minutes': default_minutes,
                'completed_at': timezone.now().isoformat(),
            })

            payload_settings = dict(app_settings)
            payload_settings['onboarding'] = onboarding_settings

            try:
                save_resp = _api_post(request, '/api/clients/settings/', {'app_settings': payload_settings})
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code == 200:
                    saved_settings = save_resp.json() if isinstance(save_resp.json(), dict) else payload_settings
                    request.session['app_settings'] = saved_settings
                    request.session.modified = True

                    # Optional payroll policy sync from onboarding selection.
                    payroll_payload = _derive_policy_from_onboarding(saved_settings)
                    try:
                        existing_resp = _api_get(request, '/api/payroll-policy/')
                        if payroll_payload and existing_resp.status_code == 200:
                            existing_payload = existing_resp.json()
                            existing_rows = (
                                existing_payload.get('results', existing_payload)
                                if isinstance(existing_payload, dict) else existing_payload
                            )
                            if existing_rows:
                                _api_put(request, f"/api/payroll-policy/{existing_rows[0].get('id')}/", payroll_payload)
                            else:
                                _api_post(request, '/api/payroll-policy/', payroll_payload)
                    except requests.exceptions.ConnectionError:
                        pass

                    _flash(request, 'Organization setup completed.', 'success')
                    return redirect('dashboard')
                errors = _error_list_from_response(save_resp, 'Failed to save organization setup.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'onboarding/org_setup.html', {
        'errors': errors,
        'selected_mode': selected_mode,
        'default_hours': f'{default_hours:02d}',
        'default_minutes': f'{default_minutes:02d}',
        **_get_context(request),
    })


def attendance_template_v2(request):
    if not request.session.get('access_token'):
        return redirect('login')

    if not _has_any_module_permission(
        request,
        ['attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete'],
    ):
        _flash(request, 'You do not have permission to access Attendance Template.', 'error')
        return redirect('dashboard')

    addon_redirect = _require_addon(request, 'attendance')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []

    app_settings = request.session.get('app_settings')
    if not isinstance(app_settings, dict):
        app_settings = _load_client_app_settings(request)
        request.session['app_settings'] = app_settings
        request.session.modified = True

    defaults = {
        'name': '',
        'attendance_mode': 'manual_attendance',
        'holiday_rule': 'no_paid_holiday_attendance',
        'track_in_out_enabled': False,
        'no_attendance_without_punch_out': False,
        'allow_multiple_punches': False,
        'auto_approval_enabled': False,
        'auto_approve_after_days': 3,
        'mark_absent_previous_days_enabled': False,
        'mark_absent_after_days': 2,
        'effective_working_hours_rule': 'do_not_show',
    }
    saved_template = app_settings.get('attendance_template_v2')
    if isinstance(saved_template, dict):
        defaults.update(saved_template)

    if request.method == 'POST':
        truthy = {'1', 'true', 'yes', 'on'}

        defaults['name'] = (request.POST.get('name') or '').strip()
        defaults['attendance_mode'] = (request.POST.get('attendance_mode') or '').strip()
        defaults['holiday_rule'] = (request.POST.get('holiday_rule') or '').strip()
        defaults['track_in_out_enabled'] = str(request.POST.get('track_in_out_enabled') or '').strip().lower() in truthy
        defaults['no_attendance_without_punch_out'] = str(request.POST.get('no_attendance_without_punch_out') or '').strip().lower() in truthy
        defaults['allow_multiple_punches'] = str(request.POST.get('allow_multiple_punches') or '').strip().lower() in truthy
        defaults['auto_approval_enabled'] = str(request.POST.get('auto_approval_enabled') or '').strip().lower() in truthy
        defaults['mark_absent_previous_days_enabled'] = str(request.POST.get('mark_absent_previous_days_enabled') or '').strip().lower() in truthy
        defaults['effective_working_hours_rule'] = (request.POST.get('effective_working_hours_rule') or '').strip()

        try:
            defaults['auto_approve_after_days'] = int((request.POST.get('auto_approve_after_days') or '3').strip())
        except (TypeError, ValueError):
            defaults['auto_approve_after_days'] = 3

        try:
            defaults['mark_absent_after_days'] = int((request.POST.get('mark_absent_after_days') or '2').strip())
        except (TypeError, ValueError):
            defaults['mark_absent_after_days'] = 2

        if not defaults['name']:
            errors.append('Template name is required.')

        if defaults['attendance_mode'] not in {
            'mark_present_default',
            'manual_attendance',
            'location_based',
            'selfie_location_based',
        }:
            errors.append('Select a valid attendance mode.')

        if defaults['holiday_rule'] not in {
            'no_paid_holiday_attendance',
            'comp_off',
            'allow_paid_holiday_attendance',
        }:
            errors.append('Select a valid attendance-on-holidays rule.')

        if defaults['effective_working_hours_rule'] not in {
            'do_not_show',
            'full_day',
            'half_day',
            'custom',
        }:
            errors.append('Select a valid effective working-hours rule.')

        if defaults['auto_approve_after_days'] < 1 or defaults['auto_approve_after_days'] > 365:
            errors.append('Auto approve after days must be between 1 and 365.')
        if defaults['mark_absent_after_days'] < 1 or defaults['mark_absent_after_days'] > 365:
            errors.append('Mark absent after days must be between 1 and 365.')
        if defaults['allow_multiple_punches'] and not defaults['track_in_out_enabled']:
            errors.append('Enable Track In & Out Time before allowing multiple punches.')

        if not errors:
            payload_settings = dict(app_settings)
            template_payload = dict(defaults)
            template_payload['updated_at'] = timezone.now().isoformat()
            if not template_payload.get('created_at'):
                template_payload['created_at'] = timezone.now().isoformat()
            payload_settings['attendance_template_v2'] = template_payload

            try:
                save_resp = _api_post(request, '/api/clients/settings/', {'app_settings': payload_settings})
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code == 200:
                    saved_settings = save_resp.json() if isinstance(save_resp.json(), dict) else payload_settings
                    request.session['app_settings'] = saved_settings
                    request.session.modified = True
                    _flash(request, 'Attendance Template V2 saved successfully.', 'success')
                    return redirect('attendance_template_v2')
                errors = _error_list_from_response(save_resp, 'Failed to save Attendance Template V2.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'attendance/template_v2.html', {
        'template_data': defaults,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


def dashboard(request):
    messages = _pop_messages(request)
    auto_clockout_alerts = []
    today = timezone.localdate()
    current_month_label = today.strftime('%B %Y')

    emp_count = 0
    cf_count = 0
    present_today = 0
    absent_today = 0
    on_leave_today = 0
    pending_leave_approvals = 0
    attendance_model_id = None
    total_branch_count = 0
    total_department_count = 0
    total_promotions = 0
    terminations_this_month = 0

    recent_employees = []
    recent_leave_applications = []
    employees_on_leave = []
    missing_attendance_today = []
    department_distribution = []
    holiday_calendar_weeks = []
    announcements = [
        {
            'title': 'Monthly Compliance Reminder',
            'content': 'Please complete pending attendance regularization and leave approvals before month end.',
            'date': today.isoformat(),
        },
        {
            'title': 'Payroll Processing Window',
            'content': 'Payroll review and lock window remains open for the final three business days of the month.',
            'date': today.isoformat(),
        },
        {
            'title': 'Document Verification Drive',
            'content': 'Employees with pending KYC documents should upload through public links this week.',
            'date': today.isoformat(),
        },
    ]

    employees_rows = []
    custom_fields_rows = []
    leaves_rows = []
    holidays_rows = []
    present_employee_ids = set()
    on_leave_employee_ids = set()

    try:
        emp_resp = _api_get(request, '/api/employees/')
        cf_resp = _api_get(request, '/api/custom-fields/')

        redirect_resp = _handle_unauthorized(emp_resp, request)
        if redirect_resp:
            return redirect_resp

        if emp_resp.status_code == 200:
            emp_payload = emp_resp.json()
            employees_rows = emp_payload.get('results', emp_payload) if isinstance(emp_payload, dict) else emp_payload
            emp_count = emp_payload.get('count', len(employees_rows)) if isinstance(emp_payload, dict) else len(employees_rows)

        if cf_resp.status_code == 200:
            cf_payload = cf_resp.json()
            custom_fields_rows = cf_payload.get('results', cf_payload) if isinstance(cf_payload, dict) else cf_payload
            cf_count = cf_payload.get('count', len(custom_fields_rows)) if isinstance(cf_payload, dict) else len(custom_fields_rows)

        leave_resp = _api_get(request, '/api/leaves/')
        if leave_resp.status_code == 200:
            leave_payload = leave_resp.json()
            leaves_rows = leave_payload.get('results', leave_payload) if isinstance(leave_payload, dict) else leave_payload

        holiday_resp = _api_get(request, '/api/holidays/')
        if holiday_resp.status_code == 200:
            holiday_payload = holiday_resp.json()
            holidays_rows = holiday_payload.get('results', holiday_payload) if isinstance(holiday_payload, dict) else holiday_payload

        # Attendance (present today) from dynamic attendance model records.
        dm_resp = _api_get(request, '/api/dynamic-models/')
        if dm_resp.status_code == 200:
            dm_payload = dm_resp.json()
            dm_rows = dm_payload.get('results', dm_payload) if isinstance(dm_payload, dict) else dm_payload
            attendance_model = next((m for m in dm_rows if str(m.get('slug', '')).lower() == 'attendance'), None)
            if attendance_model:
                attendance_model_id = attendance_model.get('id')
                rec_resp = _api_get(request, '/api/dynamic-records/', params={'dynamic_model': attendance_model.get('id')})
                if rec_resp.status_code == 200:
                    rec_payload = rec_resp.json()
                    rec_rows = rec_payload.get('results', rec_payload) if isinstance(rec_payload, dict) else rec_payload
                    for rec in rec_rows or []:
                        data = rec.get('data') or {}
                        att_date = str(data.get('attendance_date') or '')
                        if att_date != today.isoformat():
                            continue
                        status = str(data.get('status') or '').strip().lower()
                        if status == 'present' or data.get('check_in'):
                            present_employee_ids.add(str(rec.get('employee')))

        employee_by_id = {str(e.get('id')): e for e in employees_rows or []}

        # Leave metrics and recent leave entries.
        recent_leave_temp = []
        for row in leaves_rows or []:
            status = str(row.get('status') or '').strip().lower()
            if status == 'pending':
                pending_leave_approvals += 1

            start_raw = str(row.get('start_date') or '')
            end_raw = str(row.get('end_date') or '')
            try:
                start_dt = datetime.date.fromisoformat(start_raw)
                end_dt = datetime.date.fromisoformat(end_raw)
            except ValueError:
                start_dt = None
                end_dt = None

            if start_dt and end_dt and start_dt <= today <= end_dt and status in ('approved', 'pending'):
                emp_id = str(row.get('employee') or '')
                if emp_id:
                    on_leave_employee_ids.add(emp_id)

            sort_key = str(row.get('created_at') or '') or start_raw
            recent_leave_temp.append((sort_key, row))

        recent_leave_temp.sort(key=lambda item: item[0], reverse=True)
        recent_leave_applications = [row for _, row in recent_leave_temp[:8]]

        employees_on_leave = []
        for emp_id in list(on_leave_employee_ids)[:10]:
            emp = employee_by_id.get(emp_id, {})
            employees_on_leave.append({
                'name': ((emp.get('first_name') or '') + ' ' + (emp.get('last_name') or '')).strip() or (emp.get('email') or f'Employee #{emp_id}'),
                'email': emp.get('email') or '-',
                'id': emp_id,
            })

        missing_attendance_today = []
        for emp in employees_rows or []:
            emp_id = str(emp.get('id'))
            if emp_id in present_employee_ids or emp_id in on_leave_employee_ids:
                continue
            missing_attendance_today.append({
                'id': emp_id,
                'name': ((emp.get('first_name') or '') + ' ' + (emp.get('last_name') or '')).strip() or (emp.get('email') or f'Employee #{emp_id}'),
                'email': emp.get('email') or '-',
            })
        missing_attendance_today = missing_attendance_today[:10]

        present_today = len(present_employee_ids)
        on_leave_today = len(on_leave_employee_ids)
        absent_today = max(emp_count - present_today - on_leave_today, 0)

        # Derived distributions.
        dept_counter = {}
        branch_set = set()
        for emp in employees_rows or []:
            dept_name = (
                emp.get('department_name')
                or emp.get('department')
                or emp.get('client_role_name')
                or 'General'
            )
            dept_counter[dept_name] = dept_counter.get(dept_name, 0) + 1
            branch_name = emp.get('branch_name') or emp.get('branch') or ''
            if branch_name:
                branch_set.add(str(branch_name))

        total_department_count = len(dept_counter)
        total_branch_count = len(branch_set) if branch_set else (1 if emp_count else 0)
        for name, count in sorted(dept_counter.items(), key=lambda item: item[1], reverse=True):
            percent = (count * 100.0 / emp_count) if emp_count else 0
            department_distribution.append({'name': name, 'count': count, 'percent': round(percent, 1)})
        department_distribution = department_distribution[:10]

        # Placeholder business KPIs until dedicated modules exist.
        total_promotions = 0
        terminations_this_month = 0

        # Calendar matrix for current month with holiday tags.
        holiday_map = {}
        month_cal = calendar.Calendar(firstweekday=6)  # Sunday start
        first_day = datetime.date(today.year, today.month, 1)
        last_day = datetime.date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

        for row in holidays_rows or []:
            if str(row.get('is_active', True)).lower() == 'false':
                continue
            name = str(row.get('name') or 'Holiday').strip()
            start_raw = str(row.get('start_date') or '')
            end_raw = str(row.get('end_date') or '')
            try:
                start_dt = datetime.date.fromisoformat(start_raw)
                end_dt = datetime.date.fromisoformat(end_raw)
            except ValueError:
                continue
            cur = max(start_dt, first_day)
            cap = min(end_dt, last_day)
            while cur <= cap:
                holiday_map.setdefault(cur.isoformat(), []).append(name)
                cur += datetime.timedelta(days=1)

        for week in month_cal.monthdatescalendar(today.year, today.month):
            cells = []
            for day in week:
                day_key = day.isoformat()
                cells.append({
                    'day': day.day,
                    'in_month': day.month == today.month,
                    'is_today': day == today,
                    'holidays': holiday_map.get(day_key, []),
                })
            holiday_calendar_weeks.append(cells)

        recent_employees = sorted(
            employees_rows or [],
            key=lambda item: str(item.get('joining_date') or ''),
            reverse=True
        )[:5]
        auto_clockout_alerts = _load_auto_clockout_alerts(request, limit=6)

    except requests.exceptions.ConnectionError:
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    quick_actions = [
        {'label': 'Add New Employee', 'url': 'employee_create'},
        {'label': 'Mark Attendance', 'url': 'attendance_mark'},
        {'label': 'Apply for Leave', 'url': 'leave_create'},
        {'label': 'Process Payroll', 'url': 'payroll_list'},
        {'label': 'Open Documents', 'url': 'document_list'},
        {'label': 'Import / Export', 'url': 'import_export_page'},
    ]

    return render(request, 'dashboard.html', {
        'emp_count': emp_count,
        'cf_count': cf_count,
        'present_today': present_today,
        'absent_today': absent_today,
        'on_leave_today': on_leave_today,
        'pending_leave_approvals': pending_leave_approvals,
        'attendance_model_id': attendance_model_id,
        'total_branch_count': total_branch_count,
        'total_department_count': total_department_count,
        'total_promotions': total_promotions,
        'terminations_this_month': terminations_this_month,
        'recent_employees': recent_employees,
        'auto_clockout_alerts': auto_clockout_alerts,
        'department_distribution': department_distribution,
        'quick_actions': quick_actions,
        'employees_on_leave': employees_on_leave,
        'missing_attendance_today': missing_attendance_today,
        'holiday_calendar_weeks': holiday_calendar_weeks,
        'recent_leave_applications': recent_leave_applications,
        'announcements': announcements,
        'current_month_label': current_month_label,
        'messages': messages,
        **_get_context(request),
    })


def policy_page(request):
    permission_redirect = _require_module_permission(request, 'policy.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'policy')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    policies = []
    edit_item = None
    search_q = (request.GET.get('q') or '').strip()
    category_q = (request.GET.get('category') or '').strip()
    selected_active = (request.GET.get('is_active') or '').strip().lower()
    edit_id = (request.GET.get('edit') or '').strip()

    role = request.session.get('role', 'employee')
    client_id = request.session.get('client_id')
    params = {}
    if search_q:
        params['search'] = search_q
    if category_q:
        params['category'] = category_q
    if selected_active in ('true', 'false'):
        params['is_active'] = selected_active
    if role == 'superadmin' and client_id:
        params['client'] = client_id

    try:
        resp = _api_get(request, '/api/company-policies/', params=params or None)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            policies = payload.get('results', payload) if isinstance(payload, dict) else payload
        else:
            errors = _error_list_from_response(resp, 'Failed to load company policies.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if edit_id:
        edit_item = next((row for row in policies if str(row.get('id')) == edit_id), None)

    if request.method == 'POST':
        edit_id = (request.POST.get('edit_id') or '').strip()
        permission_key = 'policy.edit' if edit_id else 'policy.create'
        permission_redirect = _require_module_permission(request, permission_key)
        if permission_redirect:
            return permission_redirect

        payload = {
            'title': (request.POST.get('title') or '').strip(),
            'category': (request.POST.get('category') or '').strip(),
            'content': (request.POST.get('content') or '').strip(),
            'is_active': str(request.POST.get('is_active') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
            'image_url': (request.POST.get('existing_image_url') or '').strip(),
            'document_url': (request.POST.get('existing_document_url') or '').strip(),
        }

        if role == 'superadmin':
            if client_id:
                payload['client'] = client_id
            else:
                errors = ['Select a client at login before creating policy.']

        image_file = request.FILES.get('image_file')
        if image_file:
            payload['image_url'] = _store_uploaded_dynamic_file(image_file, folder='policy/images')

        document_file = request.FILES.get('document_file')
        if document_file:
            payload['document_url'] = _store_uploaded_dynamic_file(document_file, folder='policy/documents')

        if not errors:
            try:
                if edit_id:
                    save_resp = _api_put(request, f'/api/company-policies/{edit_id}/', payload)
                else:
                    save_resp = _api_post(request, '/api/company-policies/', payload)
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code in (200, 201):
                    _flash(request, 'Policy saved successfully.', 'success')
                    return redirect('policy_page')
                errors = _error_list_from_response(save_resp, 'Failed to save policy.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'policy/list.html', {
        'policies': policies,
        'errors': errors,
        'messages': messages,
        'search_q': search_q,
        'category_q': category_q,
        'selected_active': selected_active,
        'edit_item': edit_item,
        **_get_context(request),
    })


@require_POST
def policy_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'policy.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'policy')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/company-policies/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Policy deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete policy.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('policy_page')


def document_list(request):
    permission_redirect = _require_module_permission(request, 'documents.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'documents')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    documents = []
    requests_list = []
    employee_email_options = []
    edit_item = None
    search_q = (request.GET.get('q') or '').strip()
    category_q = (request.GET.get('category') or '').strip()
    selected_status = (request.GET.get('status') or '').strip().lower()
    selected_uploader = (request.GET.get('uploader') or '').strip()
    edit_id = (request.GET.get('edit') or '').strip()
    uploader_options = []

    role = request.session.get('role', 'employee')
    client_id = request.session.get('client_id')

    params = {}
    if search_q:
        params['search'] = search_q
    if category_q:
        params['category'] = category_q
    if selected_status in ('pending', 'approved', 'rejected'):
        params['status'] = selected_status
    if role == 'superadmin' and client_id:
        params['client'] = client_id

    try:
        doc_resp = _api_get(request, '/api/documents/', params=params or None)
        redir = _handle_unauthorized(doc_resp, request)
        if redir:
            return redir
        if doc_resp.status_code == 200:
            payload = doc_resp.json()
            documents = payload.get('results', payload) if isinstance(payload, dict) else payload
            uploader_seen = set()
            for row in documents or []:
                uploader_name = str(row.get('uploaded_by_username') or row.get('uploader_name') or '').strip()
                if not uploader_name:
                    continue
                lowered = uploader_name.lower()
                if lowered in uploader_seen:
                    continue
                uploader_seen.add(lowered)
                uploader_options.append(uploader_name)
            uploader_options = sorted(uploader_options, key=lambda v: v.lower())
            if selected_uploader:
                sel = selected_uploader.lower()
                documents = [
                    row for row in (documents or [])
                    if str(row.get('uploaded_by_username') or row.get('uploader_name') or '').strip().lower() == sel
                ]
        else:
            errors = _error_list_from_response(doc_resp, 'Failed to load documents.')

        req_params = {}
        if role == 'superadmin' and client_id:
            req_params['client'] = client_id
        req_resp = _api_get(request, '/api/document-upload-requests/', params=req_params or None)
        redir = _handle_unauthorized(req_resp, request)
        if redir:
            return redir
        if req_resp.status_code == 200:
            payload = req_resp.json()
            requests_list = payload.get('results', payload) if isinstance(payload, dict) else payload

        emp_params = {}
        if role == 'superadmin' and client_id:
            emp_params['client'] = client_id
        emp_resp = _api_get(request, '/api/employees/', params=emp_params or None)
        redir = _handle_unauthorized(emp_resp, request)
        if redir:
            return redir
        if emp_resp.status_code == 200:
            emp_payload = emp_resp.json()
            employees = emp_payload.get('results', emp_payload) if isinstance(emp_payload, dict) else emp_payload
            seen_emails = set()
            for emp in employees or []:
                email = str(emp.get('email') or '').strip()
                if not email:
                    continue
                lowered = email.lower()
                if lowered in seen_emails:
                    continue
                seen_emails.add(lowered)
                first_name = str(emp.get('first_name') or '').strip()
                last_name = str(emp.get('last_name') or '').strip()
                full_name = f'{first_name} {last_name}'.strip()
                employee_email_options.append({
                    'email': email,
                    'name': full_name,
                })
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if edit_id:
        edit_item = next((row for row in documents if str(row.get('id')) == edit_id), None)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'save_document':
            edit_id = (request.POST.get('edit_id') or '').strip()
            permission_key = 'documents.edit' if edit_id else 'documents.create'
            permission_redirect = _require_module_permission(request, permission_key)
            if permission_redirect:
                return permission_redirect

            payload = {
                'title': (request.POST.get('title') or '').strip(),
                'category': (request.POST.get('category') or '').strip(),
                'effective_date': (request.POST.get('effective_date') or '').strip() or None,
                'status': (request.POST.get('status') or 'pending').strip().lower() or 'pending',
                'notes': (request.POST.get('notes') or '').strip(),
                'file_url': (request.POST.get('existing_file_url') or '').strip(),
            }
            if role == 'superadmin' and client_id:
                payload['client'] = client_id

            file_obj = request.FILES.get('file')
            if file_obj:
                payload['file_url'] = _store_uploaded_dynamic_file(file_obj, folder='documents/files')

            try:
                if edit_id:
                    save_resp = _api_put(request, f'/api/documents/{edit_id}/', payload)
                else:
                    save_resp = _api_post(request, '/api/documents/', payload)
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code in (200, 201):
                    _flash(request, 'Document saved successfully.', 'success')
                    return redirect('document_list')
                errors = _error_list_from_response(save_resp, 'Failed to save document.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

        elif action == 'create_link':
            permission_redirect = _require_module_permission(request, 'documents.create')
            if permission_redirect:
                return permission_redirect

            selected_emails = [str(v).strip() for v in request.POST.getlist('request_emails') if str(v).strip()]
            manual_raw = (request.POST.get('request_email') or '').strip()
            manual_emails = []
            if manual_raw:
                manual_emails = [part.strip() for part in re.split(r'[,;\s]+', manual_raw) if part.strip()]

            unique_emails = []
            seen = set()
            for email in (selected_emails + manual_emails):
                lowered = email.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                unique_emails.append(email)

            valid_emails = []
            invalid_emails = []
            for email in unique_emails:
                try:
                    validate_email(email)
                    valid_emails.append(email)
                except ValidationError:
                    invalid_emails.append(email)

            if not valid_emails:
                errors = ['Select at least one valid recipient email to send upload links.']
                return render(request, 'documents/list.html', {
                    'documents': documents,
                    'requests_list': requests_list,
                    'employee_email_options': employee_email_options,
                    'edit_item': edit_item,
                    'search_q': search_q,
                    'category_q': category_q,
                    'selected_status': selected_status,
                    'selected_uploader': selected_uploader,
                    'uploader_options': uploader_options,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            days_raw = (request.POST.get('expires_in_days') or '').strip()
            expires_at = None
            if days_raw:
                try:
                    days_int = max(1, min(365, int(days_raw)))
                    expires_at = (timezone.now() + datetime.timedelta(days=days_int)).isoformat()
                except (TypeError, ValueError):
                    expires_at = None

            payload = {
                'title': (request.POST.get('request_title') or '').strip(),
                'category': (request.POST.get('request_category') or '').strip(),
                'notes': (request.POST.get('request_notes') or '').strip(),
                'is_active': True,
            }
            selected_doc_types = [str(v).strip() for v in request.POST.getlist('request_doc_types') if str(v).strip()]
            cleaned_doc_types = []
            for doc_type in selected_doc_types:
                if doc_type not in cleaned_doc_types:
                    cleaned_doc_types.append(doc_type)
            if cleaned_doc_types:
                payload['requested_doc_types'] = cleaned_doc_types[:20]

            if expires_at:
                payload['expires_at'] = expires_at
            if role == 'superadmin' and client_id:
                payload['client'] = client_id

            try:
                created_count = 0
                mailed_count = 0
                failed_recipients = []

                for recipient_email in valid_emails:
                    single_payload = dict(payload)
                    single_payload['request_email'] = recipient_email
                    link_resp = _api_post(request, '/api/document-upload-requests/', single_payload)
                    redir = _handle_unauthorized(link_resp, request)
                    if redir:
                        return redir
                    if link_resp.status_code not in (200, 201):
                        failed_recipients.append(recipient_email)
                        continue

                    created_count += 1
                    data = link_resp.json() if hasattr(link_resp, 'json') else {}
                    upload_url = str((data or {}).get('upload_url') or '').strip()
                    title = single_payload.get('title') or 'Document Upload Request'
                    category = single_payload.get('category') or '-'
                    notes = single_payload.get('notes') or '-'
                    requested_docs = single_payload.get('requested_doc_types') or []
                    expires_text = 'No expiry' if not expires_at else str(expires_at)

                    if upload_url:
                        try:
                            send_branded_email(
                                subject=f'Document Upload Link: {title}',
                                recipient_list=[recipient_email],
                                heading='Document Upload Request',
                                greeting='Hello,',
                                lines=[
                                    f'Title: {title}',
                                    f'Category: {category}',
                                    f'Notes: {notes}',
                                    f'Requested Documents: {", ".join(requested_docs) if requested_docs else "-"}',
                                    f'Expires At: {expires_text}',
                                ],
                                cta_text='Upload Document',
                                cta_url=upload_url,
                                closing='Please use this secure link to upload your document.',
                                app_settings=request.session.get('app_settings', {}),
                                fail_silently=False,
                            )
                            mailed_count += 1
                        except Exception:
                            failed_recipients.append(recipient_email)

                if invalid_emails:
                    _flash(request, f'Ignored invalid emails: {", ".join(invalid_emails)}', 'error')
                if created_count == 0:
                    errors = ['Failed to create upload links for selected recipients.']
                    return render(request, 'documents/list.html', {
                        'documents': documents,
                        'requests_list': requests_list,
                        'employee_email_options': employee_email_options,
                        'edit_item': edit_item,
                        'search_q': search_q,
                        'category_q': category_q,
                        'selected_status': selected_status,
                        'selected_uploader': selected_uploader,
                        'uploader_options': uploader_options,
                        'errors': errors,
                        'messages': messages,
                        **_get_context(request),
                    })

                if failed_recipients:
                    _flash(
                        request,
                        f'Created {created_count} link(s), sent {mailed_count} email(s). Failed recipients: {", ".join(failed_recipients)}',
                        'error',
                    )
                else:
                    _flash(request, f'Created {created_count} link(s) and sent {mailed_count} email(s) successfully.', 'success')

                    return redirect('document_list')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

        elif action == 'send_offer_letter_pdf':
            permission_redirect = _require_module_permission(request, 'documents.create')
            if permission_redirect:
                return permission_redirect

            candidate_name = (request.POST.get('offer_candidate_name') or '').strip()
            recipient_email = (request.POST.get('offer_recipient_email') or '').strip()
            state_name = (request.POST.get('offer_state') or '').strip() or 'Gujarat'
            annual_income_raw = (request.POST.get('offer_annual_income') or '').strip()
            components_raw = (request.POST.get('offer_components_json') or '').strip()

            if not candidate_name:
                errors = ['Candidate name is required for offer letter.']
            if not recipient_email:
                errors.append('Recipient email is required.')
            else:
                try:
                    validate_email(recipient_email)
                except ValidationError:
                    errors.append('Recipient email is invalid.')

            try:
                annual_income = float(annual_income_raw or 0)
                if annual_income <= 0:
                    errors.append('Annual income must be greater than 0.')
            except (TypeError, ValueError):
                annual_income = 0
                errors.append('Annual income must be a valid number.')

            components = []
            if components_raw:
                try:
                    parsed = json.loads(components_raw)
                    if isinstance(parsed, list):
                        for row in parsed:
                            if not isinstance(row, dict):
                                continue
                            name = str(row.get('name') or '').strip()
                            if not name:
                                continue
                            try:
                                pct = float(row.get('pct') or 0)
                            except (TypeError, ValueError):
                                pct = 0
                            components.append({'name': name, 'pct': pct})
                except json.JSONDecodeError:
                    errors.append('Invalid component data. Please calculate again and submit.')

            if not components:
                errors.append('Add at least one salary component.')

            if not errors:
                try:
                    pdf_bytes = _build_offer_letter_pdf(candidate_name, state_name, annual_income, components)
                    file_name = f"offer_letter_{slugify(candidate_name) or 'candidate'}.pdf"
                    send_branded_email(
                        subject=f'Offer Letter - {candidate_name}',
                        recipient_list=[recipient_email],
                        heading='Offer Letter',
                        greeting='Hello,',
                        lines=[
                            f'Please find attached your offer letter summary.',
                            f'Candidate: {candidate_name}',
                            f'State: {state_name}',
                            f'Annual Income (CTC): INR {annual_income:,.2f}',
                        ],
                        closing='Regards, HR Team',
                        app_settings=request.session.get('app_settings', {}),
                        attachments=[(file_name, pdf_bytes, 'application/pdf')],
                        fail_silently=False,
                    )
                    _flash(request, f'Offer letter PDF sent successfully to {recipient_email}.', 'success')
                    return redirect('document_list')
                except Exception:
                    errors = ['Failed to generate or send offer letter PDF.']

    return render(request, 'documents/list.html', {
        'documents': documents,
        'requests_list': requests_list,
        'employee_email_options': employee_email_options,
        'edit_item': edit_item,
        'search_q': search_q,
        'category_q': category_q,
        'selected_status': selected_status,
        'selected_uploader': selected_uploader,
        'uploader_options': uploader_options,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


@require_POST
def document_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'documents.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'documents')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/documents/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Document deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete document.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('document_list')


@require_POST
def document_request_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'documents.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'documents')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/document-upload-requests/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Upload link deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete upload link.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('document_list')


def document_upload_page(request, token):
    info = {}
    errors = []
    success_message = ''
    token = str(token).strip()

    try:
        resp = _api_request('GET', f'/api/document-upload/{token}/', host=request.get_host())
        if resp.status_code == 200:
            info = resp.json() if isinstance(resp.json(), dict) else {}
        else:
            errors = _error_list_from_response(resp, 'Upload link is invalid.')
    except requests.exceptions.ConnectionError:
        errors = ['Server unavailable. Please try again later.']

    if request.method == 'POST' and not errors:
        payload = {
            'title': (request.POST.get('title') or '').strip() or info.get('title', ''),
            'category': (request.POST.get('category') or '').strip() or info.get('category', ''),
            'effective_date': (request.POST.get('effective_date') or '').strip(),
            'uploader_name': (request.POST.get('uploader_name') or '').strip(),
            'uploader_email': (request.POST.get('uploader_email') or '').strip(),
            'notes': (request.POST.get('notes') or '').strip() or info.get('notes', ''),
        }
        doc_types = request.POST.getlist('doc_type')
        doc_files = request.FILES.getlist('doc_file')
        requested_doc_types = [
            str(item).strip()
            for item in (info.get('requested_doc_types') or [])
            if str(item).strip()
        ]

        documents_payload = []
        max_len = max(len(doc_types), len(doc_files))
        for idx in range(max_len):
            current_type = str(doc_types[idx]).strip() if idx < len(doc_types) else ''
            current_file = doc_files[idx] if idx < len(doc_files) else None
            if not current_file:
                continue
            if requested_doc_types and current_type not in requested_doc_types:
                errors = [f'Invalid document type selected: {current_type or "Unknown"}']
                break
            file_url = _store_uploaded_dynamic_file(current_file, folder='documents/public')
            documents_payload.append({
                'doc_type': current_type,
                'file_url': file_url,
            })

        if not errors:
            if documents_payload:
                payload['documents'] = documents_payload
            else:
                upload_files = request.FILES.getlist('files')
                if not upload_files:
                    single_file = request.FILES.get('file')
                    if single_file:
                        upload_files = [single_file]
                if upload_files:
                    payload['file_urls'] = [
                        _store_uploaded_dynamic_file(upload_file, folder='documents/public')
                        for upload_file in upload_files
                    ]

        if not errors:
            try:
                post_resp = _api_request('POST', f'/api/document-upload/{token}/', data=payload, host=request.get_host())
                if post_resp.status_code in (200, 201):
                    uploaded_count = 0
                    try:
                        response_data = post_resp.json()
                        if isinstance(response_data, dict):
                            uploaded_count = int(response_data.get('uploaded_count') or 0)
                    except Exception:
                        uploaded_count = 0
                    if uploaded_count > 1:
                        success_message = f'{uploaded_count} documents uploaded successfully. You can close this page.'
                    else:
                        success_message = 'Document uploaded successfully. You can close this page.'
                else:
                    errors = _error_list_from_response(post_resp, 'Failed to upload document.')
            except requests.exceptions.ConnectionError:
                errors = ['Server unavailable. Please try again later.']

    return render(request, 'documents/public_upload.html', {
        'info': info,
        'errors': errors,
        'success_message': success_message,
    })


def settings_page(request):
    role = request.session.get('role')
    if role not in ('admin', 'superadmin'):
        return render(request, 'errors/403.html', status=403)
    addon_redirect = _require_addon(request, 'settings')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    settings_data = {}
    is_edit_mode = False

    client_id = request.session.get('client_id')
    if role == 'superadmin' and not client_id:
        errors.append('Select a client at login to manage client settings.')
    params = {'client_id': client_id} if role == 'superadmin' and client_id else None

    try:
        resp = _api_get(request, '/api/clients/settings/', params=params)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            settings_data = resp.json() if isinstance(resp.json(), dict) else {}
            request.session['app_settings'] = settings_data
            request.session.modified = True
        elif resp.status_code != 404:
            errors = _error_list_from_response(resp, 'Failed to load settings.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if not settings_data:
        session_settings = request.session.get('app_settings')
        if isinstance(session_settings, dict):
            settings_data = session_settings

    sidebar_logo_modules = _get_sidebar_logo_modules(request)
    sidebar_module_icon_keys_csv = ','.join([str(item.get('key') or '').strip() for item in sidebar_logo_modules if str(item.get('key') or '').strip()])

    if request.method == 'POST':
        is_edit_mode = True
        def _bool_field(name):
            return str(request.POST.get(name) or '').strip().lower() in ('1', 'true', 'yes', 'on')
        def _int_field(name, default=14, min_value=12, max_value=20):
            raw = str(request.POST.get(name) or '').strip()
            try:
                value = int(raw or default)
            except (TypeError, ValueError):
                value = default
            return max(min_value, min(max_value, value))

        existing_brand = settings_data.get('brand') if isinstance(settings_data, dict) else {}
        if not isinstance(existing_brand, dict):
            existing_brand = {}
        existing_ui = settings_data.get('ui') if isinstance(settings_data, dict) else {}
        if not isinstance(existing_ui, dict):
            existing_ui = {}

        logo_url = (request.POST.get('logo_url') or '').strip() or existing_brand.get('logo_url', '')
        favicon_url = (request.POST.get('favicon_url') or '').strip() or existing_brand.get('favicon_url', '')
        sidebar_logo_url = (request.POST.get('sidebar_logo_url') or '').strip() or existing_ui.get('sidebar_logo_url', '')
        existing_module_icons = existing_ui.get('sidebar_module_icons') if isinstance(existing_ui.get('sidebar_module_icons'), dict) else {}
        sidebar_module_icons = dict(existing_module_icons)

        if _bool_field('remove_logo'):
            logo_url = ''
        if _bool_field('remove_favicon'):
            favicon_url = ''
        if _bool_field('remove_sidebar_logo'):
            sidebar_logo_url = ''

        logo_file = request.FILES.get('logo_file')
        if logo_file:
            logo_url = _store_uploaded_dynamic_file(logo_file, folder='brand_assets/logo')

        favicon_file = request.FILES.get('favicon_file')
        if favicon_file:
            favicon_url = _store_uploaded_dynamic_file(favicon_file, folder='brand_assets/favicon')
        sidebar_logo_file = request.FILES.get('sidebar_logo_file')
        if sidebar_logo_file:
            sidebar_logo_url = _store_uploaded_dynamic_file(sidebar_logo_file, folder='brand_assets/sidebar_logo')

        posted_keys_raw = str(request.POST.get('sidebar_module_icon_keys') or '').strip()
        module_icon_keys = [k.strip().lower() for k in posted_keys_raw.split(',') if k.strip()]
        for module_key in module_icon_keys:
            if not re.fullmatch(r'[a-z0-9_]+', module_key or ''):
                continue
            remove_name = f'remove_module_logo_{module_key}'
            url_name = f'module_logo_{module_key}_url'
            file_name = f'module_logo_{module_key}_file'

            current_url = sidebar_module_icons.get(module_key, '')
            submitted_url = (request.POST.get(url_name) or '').strip()
            next_url = submitted_url if submitted_url else current_url

            if _bool_field(remove_name):
                next_url = ''

            file_obj = request.FILES.get(file_name)
            if file_obj:
                next_url = _store_uploaded_dynamic_file(file_obj, folder=f'brand_assets/module_logo/{module_key}')

            if next_url:
                sidebar_module_icons[module_key] = next_url
            elif module_key in sidebar_module_icons:
                sidebar_module_icons.pop(module_key, None)

        payload_settings = {
            'brand': {
                'brand_name': (request.POST.get('brand_name') or '').strip(),
                'tagline': (request.POST.get('tagline') or '').strip(),
                'logo_url': logo_url,
                'favicon_url': favicon_url,
            },
            'theme': {
                'primary_color': (request.POST.get('primary_color') or '').strip(),
                'secondary_color': (request.POST.get('secondary_color') or '').strip(),
                'background_color': (request.POST.get('background_color') or '').strip(),
            },
            'ui': {
                'sidebar_variant': (request.POST.get('sidebar_variant') or 'inset').strip().lower(),
                'sidebar_style': (request.POST.get('sidebar_style') or 'plain').strip().lower(),
                'layout_direction': (request.POST.get('layout_direction') or 'ltr').strip().lower(),
                'theme_mode': (request.POST.get('theme_mode') or 'light').strip().lower(),
                'font_family': (request.POST.get('font_family') or 'inter').strip().lower(),
                'font_family_custom': (request.POST.get('font_family_custom') or '').strip(),
                'font_size_base': _int_field('font_size_base', default=14, min_value=12, max_value=20),
                'sidebar_logo_url': sidebar_logo_url,
                'sidebar_module_icons': sidebar_module_icons,
            },
            'system': {
                'timezone': (request.POST.get('timezone') or '').strip(),
                'date_format': (request.POST.get('date_format') or '').strip(),
            },
            'company': {
                'company_name': (request.POST.get('company_name') or '').strip(),
                'company_email': (request.POST.get('company_email') or '').strip(),
                'company_phone': (request.POST.get('company_phone') or '').strip(),
            },
            'currency': {
                'currency_code': (request.POST.get('currency_code') or '').strip(),
                'currency_symbol': (request.POST.get('currency_symbol') or '').strip(),
            },
            'email': {
                'from_email': (request.POST.get('from_email') or '').strip(),
                'reply_to_email': (request.POST.get('reply_to_email') or '').strip(),
            },
            'email_notifications': {
                'leave_request_email': _bool_field('leave_request_email'),
                'leave_approval_email': _bool_field('leave_approval_email'),
                'attendance_alert_email': _bool_field('attendance_alert_email'),
            },
            'stripe': {
                'publishable_key': (request.POST.get('stripe_publishable_key') or '').strip(),
                'secret_key': (request.POST.get('stripe_secret_key') or '').strip(),
                'enabled': _bool_field('stripe_enabled'),
            },
            'paypal': {
                'client_id': (request.POST.get('paypal_client_id') or '').strip(),
                'secret_key': (request.POST.get('paypal_secret_key') or '').strip(),
                'enabled': _bool_field('paypal_enabled'),
            },
        }

        payload = {'app_settings': payload_settings}
        if role == 'superadmin' and client_id:
            payload['client_id'] = client_id

        try:
            save_resp = _api_post(request, '/api/clients/settings/', payload)
            redir = _handle_unauthorized(save_resp, request)
            if redir:
                return redir
            if save_resp.status_code == 200:
                saved_settings = save_resp.json() if isinstance(save_resp.json(), dict) else {}
                request.session['app_settings'] = saved_settings
                request.session.modified = True
                _flash(request, 'Settings saved successfully.', 'success')
                return redirect('settings_page')
            errors = _error_list_from_response(save_resp, 'Failed to save settings.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'settings/list.html', {
        'settings_data': settings_data,
        'is_edit_mode': is_edit_mode,
        'sidebar_logo_modules': sidebar_logo_modules,
        'sidebar_module_icon_keys_csv': sidebar_module_icon_keys_csv,
        'messages': messages,
        'errors': errors,
        **_get_context(request),
    })


# ─────────────────────────────────────────────────────────────────
# Clients
# ─────────────────────────────────────────────────────────────────

def client_list(request):
    # Only superadmin can access clients
    if request.session.get('role') != 'superadmin':
        return render(request, 'errors/403.html', status=403)
    
    messages = _pop_messages(request)
    search_q = request.GET.get('q', '')
    params = {}
    if search_q:
        params['search'] = search_q

    try:
        resp = _api_get(request, '/api/clients/', params=params)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        data = resp.json() if resp.status_code == 200 else []
        clients = data.get('results', data) if isinstance(data, dict) else data
    except requests.exceptions.ConnectionError:
        clients = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'clients/list.html', {
        'clients': clients,
        'search_q': search_q,
        'messages': messages,
        **_get_context(request),
    })


def client_create(request):
    # Only superadmin can create clients
    if request.session.get('role') != 'superadmin':
        return render(request, 'errors/403.html', status=403)
    
    form = ClientForm()
    errors = []
    messages = _pop_messages(request)

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client_password = form.cleaned_data.get('password', '')
            admin_username = form.cleaned_data.get('admin_username', '').strip()
            admin_email = form.cleaned_data.get('admin_email', '').strip()
            admin_password = form.cleaned_data.get('admin_password', '')

            if not client_password:
                errors = ['Client password is required.']
                return render(request, 'clients/create.html', {
                    'form': form,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            if not all([admin_username, admin_email, admin_password]):
                errors = ['Admin username, admin email, and admin password are required.']
                return render(request, 'clients/create.html', {
                    'form': form,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            try:
                client_payload = {
                    'name': form.cleaned_data['name'],
                    'domain': form.cleaned_data['domain'],
                    'password': client_password,
                    'enabled_addons': form.cleaned_data.get('enabled_addons', []),
                    'role_limit': form.cleaned_data.get('role_limit') or 0,
                }
                if form.cleaned_data.get('schema_name'):
                    client_payload['schema_name'] = form.cleaned_data['schema_name']

                resp = _api_post(request, '/api/clients/', client_payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir

                if resp.status_code == 201:
                    created_client = resp.json()
                    register_payload = {
                        'username': admin_username,
                        'email': admin_email,
                        'password': admin_password,
                        'client_id': created_client.get('id'),
                        'role': 'admin',
                    }
                    reg_resp = _api_post(request, '/api/accounts/register/', register_payload)
                    if reg_resp.status_code == 201:
                        _flash(request, 'Client and client admin created successfully!', 'success')
                        return redirect('client_list')

                    # Roll back client if admin-user creation fails
                    created_client_id = created_client.get('id')
                    if created_client_id:
                        _api_delete(request, f'/api/clients/{created_client_id}/')

                    reg_error = reg_resp.json() if reg_resp.content else {'error': 'Failed to create admin user.'}
                    if isinstance(reg_error, dict):
                        errors = [f'{k}: {v}' for k, v in reg_error.items()]
                    else:
                        errors = ['Failed to create admin user.']
                else:
                    api_error = resp.json() if resp.content else {'error': 'Failed to create client.'}
                    if isinstance(api_error, dict):
                        errors = [f'{k}: {v}' for k, v in api_error.items()]
                    else:
                        errors = ['Failed to create client.']
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'clients/create.html', {
        'form': form,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


def client_edit(request, pk):
    # Only superadmin can edit clients
    if request.session.get('role') != 'superadmin':
        return render(request, 'errors/403.html', status=403)
    
    errors = []
    messages = _pop_messages(request)

    try:
        get_resp = _api_get(request, f'/api/clients/{pk}/')
        redir = _handle_unauthorized(get_resp, request)
        if redir:
            return redir

        if get_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)

        client_data = get_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'clients/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            try:
                update_payload = {
                    'name': form.cleaned_data['name'],
                    'domain': form.cleaned_data['domain'],
                    'password': form.cleaned_data['password'],
                    'enabled_addons': form.cleaned_data.get('enabled_addons', []),
                    'role_limit': form.cleaned_data.get('role_limit') or 0,
                }
                resp = _api_put(request, f'/api/clients/{pk}/', update_payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir

                if resp.status_code == 200:
                    _flash(request, 'Client updated successfully!', 'success')
                    return redirect('client_list')
                else:
                    errors = [f'{k}: {v}' for k, v in resp.json().items()]
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
    else:
        initial = dict(client_data)
        initial['enabled_addons'] = client_data.get('enabled_addons', [])
        initial['role_limit'] = client_data.get('role_limit', 0)
        form = ClientForm(initial=initial)

    return render(request, 'clients/edit.html', {
        'form': form,
        'client': client_data,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


@require_POST
def client_delete(request, pk):
    # Only superadmin can delete clients
    if request.session.get('role') != 'superadmin':
        return render(request, 'errors/403.html', status=403)
    
    try:
        resp = _api_delete(request, f'/api/clients/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        if resp.status_code == 204:
            _flash(request, 'Client deleted successfully!', 'success')
        else:
            _flash(request, 'Failed to delete client.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')

    return redirect('client_list')


def role_list(request):
    if request.session.get('role') not in ('admin', 'superadmin'):
        return render(request, 'errors/403.html', status=403)
    addon_redirect = _require_addon(request, 'role_management')
    if addon_redirect:
        return addon_redirect

    errors = []
    messages = _pop_messages(request)
    roles = []
    client_info = {}
    permission_options = []
    target_client_id = request.session.get('client_id')
    if request.session.get('role') == 'superadmin':
        target_client_id = request.GET.get('client_id') or target_client_id

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if request.session.get('role') == 'superadmin' and not target_client_id:
            errors = ['Select a client first (use ?client_id=<id> in URL).']
            action = ''
        payload = {
            'name': (request.POST.get('name') or '').strip(),
            'is_active': (request.POST.get('is_active') or '').strip().lower() not in ('false', '0', 'off'),
            'module_permissions': [str(p).strip() for p in request.POST.getlist('module_permissions') if str(p).strip()],
            'enabled_addons': _normalize_enabled_addons(request.POST.getlist('enabled_addons')),
        }
        slug_value = (request.POST.get('slug') or '').strip()
        if slug_value:
            payload['slug'] = slug_value
        sort_order_raw = (request.POST.get('sort_order') or '').strip()
        if sort_order_raw:
            payload['sort_order'] = int(sort_order_raw)
        if target_client_id:
            payload['client'] = int(target_client_id)
        if not payload.get('slug'):
            payload['slug'] = slugify(payload.get('name', ''))
        try:
            if action == 'create':
                resp = _api_post(request, '/api/client-roles/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 201:
                    _flash(request, 'Role created successfully.', 'success')
                    return redirect('role_list')
                errors = _error_list_from_response(resp, 'Failed to create role.')
            elif action == 'update':
                role_id = request.POST.get('role_id')
                resp = _api_put(request, f'/api/client-roles/{role_id}/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 200:
                    _flash(request, 'Role updated successfully.', 'success')
                    return redirect('role_list')
                errors = _error_list_from_response(resp, 'Failed to update role.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    try:
        params = {}
        if target_client_id:
            params['client'] = target_client_id
        roles_resp = _api_get(request, '/api/client-roles/', params=params)
        redir = _handle_unauthorized(roles_resp, request)
        if redir:
            return redir
        if roles_resp.status_code == 200:
            payload = roles_resp.json()
            roles = payload.get('results', payload) if isinstance(payload, dict) else payload

        if target_client_id:
            client_resp = _api_get(request, f'/api/clients/{target_client_id}/')
            if client_resp.status_code == 200:
                client_info = client_resp.json()
        permission_params = {'client': target_client_id} if request.session.get('role') == 'superadmin' and target_client_id else None
        option_resp = _api_get(request, '/api/accounts/permission-options/', params=permission_params)
        if option_resp.status_code == 200:
            permission_options = option_resp.json()
    except requests.exceptions.ConnectionError:
        errors.append('Backend server unreachable.')

    return render(request, 'roles/list.html', {
        'roles': roles,
        'client_info': client_info,
        'permission_options': permission_options,
        'addon_options': ADDON_OPTIONS,
        'target_client_id': target_client_id,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


@require_POST
def role_delete(request, pk):
    if request.session.get('role') not in ('admin', 'superadmin'):
        return render(request, 'errors/403.html', status=403)
    addon_redirect = _require_addon(request, 'role_management')
    if addon_redirect:
        return addon_redirect
    try:
        resp = _api_delete(request, f'/api/client-roles/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Role deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete role.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('role_list')


def permission_list(request):
    if request.session.get('role') != 'admin':
        return render(request, 'errors/403.html', status=403)

    messages = _pop_messages(request)
    errors = []
    users = []
    permission_options = []
    groups = []
    auto_clockout_alerts = []

    try:
        options_resp = _api_get(request, '/api/accounts/permission-options/')
        redir = _handle_unauthorized(options_resp, request)
        if redir:
            return redir
        if options_resp.status_code == 200:
            permission_options = options_resp.json()

        groups_resp = _api_get(request, '/api/account-groups/')
        redir = _handle_unauthorized(groups_resp, request)
        if redir:
            return redir
        if groups_resp.status_code == 200:
            groups_data = groups_resp.json()
            groups = groups_data.get('results', groups_data) if isinstance(groups_data, dict) else groups_data

        users_resp = _api_get(request, '/api/accounts/')
        redir = _handle_unauthorized(users_resp, request)
        if redir:
            return redir
        if users_resp.status_code == 200:
            users_data = users_resp.json()
            users = users_data.get('results', users_data) if isinstance(users_data, dict) else users_data
            users = [u for u in users if u.get('role') != 'superadmin']
            try:
                emp_resp = _api_get(request, '/api/employees/')
                if emp_resp.status_code == 200:
                    emp_payload = emp_resp.json()
                    employee_rows = (
                        emp_payload.get('results', emp_payload)
                        if isinstance(emp_payload, dict) else emp_payload
                    )
                    active_employee_emails = {
                        str(row.get('email') or '').strip().lower()
                        for row in employee_rows
                        if str(row.get('email') or '').strip()
                    }
                    users = [
                        u for u in users
                        if u.get('role') == 'admin'
                        or str((u.get('user') or {}).get('email') or '').strip().lower() in active_employee_emails
                    ]
            except requests.exceptions.ConnectionError:
                pass
        auto_clockout_alerts = _load_auto_clockout_alerts(request, limit=8)
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_group':
            try:
                payload = {
                    'name': (request.POST.get('group_name') or '').strip(),
                    'module_permissions': _normalize_module_permissions(request.POST.getlist('module_permissions')),
                    'enabled_addons': _normalize_enabled_addons(request.POST.getlist('enabled_addons')),
                }
                create_resp = _api_post(request, '/api/account-groups/', payload)
                redir = _handle_unauthorized(create_resp, request)
                if redir:
                    return redir
                if create_resp.status_code == 201:
                    _flash(request, 'Permission group created successfully.', 'success')
                    return redirect('permission_list')
                errors = _error_list_from_response(create_resp, 'Failed to create permission group.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
        elif action == 'update_group':
            group_id = request.POST.get('group_id')
            try:
                payload = {
                    'name': (request.POST.get('group_name') or '').strip(),
                    'module_permissions': _normalize_module_permissions(request.POST.getlist('module_permissions')),
                    'enabled_addons': _normalize_enabled_addons(request.POST.getlist('enabled_addons')),
                }
                update_resp = _api_put(request, f'/api/account-groups/{group_id}/', payload)
                redir = _handle_unauthorized(update_resp, request)
                if redir:
                    return redir
                if update_resp.status_code == 200:
                    _flash(request, 'Permission group updated successfully.', 'success')
                    return redirect('permission_list')
                errors = _error_list_from_response(update_resp, 'Failed to update permissions.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
        elif action == 'delete_group':
            group_id = request.POST.get('group_id')
            try:
                delete_resp = _api_delete(request, f'/api/account-groups/{group_id}/')
                redir = _handle_unauthorized(delete_resp, request)
                if redir:
                    return redir
                if delete_resp.status_code == 204:
                    _flash(request, 'Permission group deleted successfully.', 'success')
                    return redirect('permission_list')
                errors = _error_list_from_response(delete_resp, 'Failed to delete group.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
        elif action == 'assign_group':
            profile_id = request.POST.get('profile_id')
            group_id = (request.POST.get('permission_group') or '').strip()
            try:
                payload = {'permission_group': group_id}
                assign_resp = _api_post(request, f'/api/accounts/{profile_id}/assign-group/', payload)
                redir = _handle_unauthorized(assign_resp, request)
                if redir:
                    return redir
                if assign_resp.status_code == 200:
                    addon_payload = {
                        'enabled_addons': _normalize_enabled_addons(request.POST.getlist('user_enabled_addons')),
                    }
                    addon_resp = _api_post(request, f'/api/accounts/{profile_id}/set-permissions/', addon_payload)
                    redir = _handle_unauthorized(addon_resp, request)
                    if redir:
                        return redir
                    if addon_resp.status_code != 200:
                        errors = _error_list_from_response(addon_resp, 'Failed to update user add-on permissions.')
                        return render(request, 'permissions/list.html', {
                            'users': users,
                            'groups': groups,
                            'permission_options': permission_options,
                            'addon_options': ADDON_OPTIONS,
                            'auto_clockout_alerts': auto_clockout_alerts,
                            'errors': errors,
                            'messages': messages,
                            **_get_context(request),
                        })

                    target_user = next((u for u in users if str(u.get('id')) == str(profile_id)), None)
                    selected_group = next((g for g in groups if str(g.get('id')) == str(group_id)), None)
                    inferred_role = _infer_employee_role_from_group_name(
                        (selected_group or {}).get('name', '')
                    ) if selected_group else ''
                    client_roles = _load_client_roles(request)
                    target_email = str((target_user or {}).get('user', {}).get('email') or '').strip().lower()
                    if inferred_role and target_email:
                        try:
                            emp_resp = _api_get(request, '/api/employees/')
                            redir = _handle_unauthorized(emp_resp, request)
                            if redir:
                                return redir
                            if emp_resp.status_code == 200:
                                emp_data = emp_resp.json()
                                employee_rows = (
                                    emp_data.get('results', emp_data)
                                    if isinstance(emp_data, dict) else emp_data
                                )
                                linked_employee = next(
                                    (
                                        row for row in employee_rows
                                        if str(row.get('email') or '').strip().lower() == target_email
                                    ),
                                    None,
                                )
                                if linked_employee and str(linked_employee.get('role') or '').strip().lower() != inferred_role:
                                    inferred_client_role_id = _infer_client_role_id_from_group_name(
                                        (selected_group or {}).get('name', ''),
                                        client_roles,
                                    )
                                    role_update_payload = {
                                        'first_name': linked_employee.get('first_name', ''),
                                        'last_name': linked_employee.get('last_name', ''),
                                        'email': linked_employee.get('email', ''),
                                        'role': inferred_role,
                                        'client_role': int(inferred_client_role_id) if str(inferred_client_role_id).isdigit() else None,
                                        'client': linked_employee.get('client'),
                                        'hr': linked_employee.get('hr'),
                                        'manager': linked_employee.get('manager'),
                                        'joining_date': linked_employee.get('joining_date'),
                                    }
                                    _api_put(request, f"/api/employees/{linked_employee.get('id')}/", role_update_payload)
                        except requests.exceptions.ConnectionError:
                            pass

                    _flash(request, 'User group updated successfully.', 'success')
                    return redirect('permission_list')
                errors = _error_list_from_response(assign_resp, 'Failed to assign group.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'permissions/list.html', {
        'users': users,
        'groups': groups,
        'permission_options': permission_options,
        'addon_options': ADDON_OPTIONS,
        'auto_clockout_alerts': auto_clockout_alerts,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


# ─────────────────────────────────────────────────────────────────
# Employees
# ─────────────────────────────────────────────────────────────────

def employee_list(request):
    permission_redirect = _require_module_permission(request, 'employees.view')
    if permission_redirect:
        return permission_redirect
    messages = _pop_messages(request)
    search_q = request.GET.get('q', '')
    selected_role = (request.GET.get('role') or '').strip()
    client_roles = _load_client_roles(request)
    can_create_employee = (
        request.session.get('role') in ('superadmin', 'admin')
        or 'employees.create' in (request.session.get('module_permissions') or [])
    )

    create_form = EmployeeForm()
    create_errors = []
    create_custom_fields = []
    create_custom_field_values = {}
    create_client_roles = []
    create_hr_options = []
    create_manager_options = []
    create_dynamic_models = []
    create_dynamic_fields_by_model = {}
    show_employee_section = 'list'

    if can_create_employee:
        create_client_roles = _load_client_roles(request)
        role_choices = [(item['id'], item['label']) for item in create_client_roles]
        create_hr_options = _employee_assignment_options(request, 'hr')
        create_manager_options = _employee_assignment_options(request, 'manager')
        create_form.fields['role'].choices = role_choices
        create_form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
            (item['id'], item['label']) for item in create_hr_options
        ]
        create_form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
            (item['id'], item['label']) for item in create_manager_options
        ]
        create_dynamic_models, create_dynamic_fields_by_model = _get_dynamic_models_with_fields(request)
        try:
            cf_resp = _api_get(request, '/api/custom-fields/?model_name=Employee')
            if cf_resp.status_code == 200:
                cf_data = cf_resp.json()
                create_custom_fields = (
                    cf_data.get('results', cf_data) if isinstance(cf_data, dict) else cf_data
                )
        except requests.exceptions.ConnectionError:
            pass

    if request.method == 'POST' and request.POST.get('action') == 'create_employee':
        show_employee_section = 'create'
        if not can_create_employee:
            create_errors = ['You do not have permission to create employees.']
        elif not create_client_roles:
            create_errors = ['No roles found. First create at least one role from Role Management, then create employees.']
        else:
            role_choices = [(item['id'], item['label']) for item in create_client_roles]
            create_form = EmployeeForm(request.POST)
            create_form.fields['role'].choices = role_choices
            create_form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
                (item['id'], item['label']) for item in create_hr_options
            ]
            create_form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
                (item['id'], item['label']) for item in create_manager_options
            ]
            if create_form.is_valid():
                try:
                    client_id = request.session.get('client_id')
                    if not client_id:
                        create_errors = ['You are not assigned to any client. Contact your administrator.']
                    else:
                        employee_data = create_form.cleaned_data.copy()
                        selected_create_role = str(employee_data.pop('role', '')).strip()
                        hr_value = employee_data.pop('hr', '')
                        manager_value = employee_data.pop('manager', '')
                        employee_data['client'] = client_id

                        if not selected_create_role.isdigit():
                            create_errors = ['Select a valid role.']
                        else:
                            selected_role_item = next(
                                (item for item in create_client_roles if item['id'] == selected_create_role),
                                None,
                            )
                            employee_data['client_role'] = int(selected_create_role)
                            employee_data['role'] = (selected_role_item or {}).get('base_role', 'employee')
                            employee_data['hr'] = int(hr_value) if hr_value else None
                            employee_data['manager'] = int(manager_value) if manager_value else None
                            employee_data = _serialize_data(employee_data)

                            save_resp = _api_post(request, '/api/employees/', employee_data)
                            redir = _handle_unauthorized(save_resp, request)
                            if redir:
                                return redir

                            if save_resp.status_code == 201:
                                employee = save_resp.json()
                                employee_id = employee['id']

                                for cf in create_custom_fields:
                                    field_value = request.POST.get(f'custom_field_{cf["id"]}')
                                    if field_value:
                                        _api_post(request, '/api/custom-field-values/', {
                                            'employee': employee_id,
                                            'field': cf['id'],
                                            'value': field_value,
                                        })

                                _save_employee_dynamic_records(
                                    request,
                                    employee_id,
                                    create_dynamic_models,
                                    create_dynamic_fields_by_model,
                                )
                                _flash(request, 'Employee created successfully!', 'success')
                                return redirect('employee_list')
                            create_errors = _employee_error_list(save_resp, 'Failed to create employee.')
                except requests.exceptions.ConnectionError:
                    create_errors = ['Backend server unreachable.']
            else:
                create_errors = ['Please fix the highlighted form fields and try again.']
    params = {}
    if search_q:
        params['search'] = search_q
    if selected_role.isdigit():
        params['client_role'] = selected_role

    try:
        resp = _api_get(request, '/api/employees/', params=params)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        data = resp.json() if resp.status_code == 200 else []
        employees = data.get('results', data) if isinstance(data, dict) else data
    except requests.exceptions.ConnectionError:
        employees = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    current_week_leave_rows = []
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)
    session_role = request.session.get('role', 'employee')
    session_employee_role = (request.session.get('employee_role') or '').strip().lower()
    session_employee_id = request.session.get('employee_id')
    can_view_full_leave_report = (
        session_role in ('superadmin', 'admin')
        or session_employee_role in ('hr', 'manager')
    )
    try:
        leave_resp = _api_get(request, '/api/leaves/', params={'status': 'approved'})
        redir = _handle_unauthorized(leave_resp, request)
        if redir:
            return redir
        if leave_resp.status_code == 200:
            leave_data = leave_resp.json()
            leave_rows = leave_data.get('results', leave_data) if isinstance(leave_data, dict) else leave_data
            for row in leave_rows:
                if not can_view_full_leave_report:
                    if not session_employee_id or str(row.get('employee')) != str(session_employee_id):
                        continue
                try:
                    start_dt = datetime.date.fromisoformat(str(row.get('start_date')))
                    end_dt = datetime.date.fromisoformat(str(row.get('end_date')))
                except (TypeError, ValueError):
                    continue
                if end_dt < week_start or start_dt > week_end:
                    continue
                current_week_leave_rows.append(row)
            current_week_leave_rows.sort(key=lambda x: str(x.get('start_date') or ''))
    except requests.exceptions.ConnectionError:
        pass

    return render(request, 'employees/list.html', {
        'employees': employees,
        'current_week_leave_rows': current_week_leave_rows,
        'can_view_full_leave_report': can_view_full_leave_report,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'search_q': search_q,
        'selected_role': selected_role,
        'role_filter_options': client_roles,
        'can_create_employee': can_create_employee,
        'show_employee_section': show_employee_section,
        'create_form': create_form,
        'create_errors': create_errors,
        'create_custom_fields': create_custom_fields,
        'create_custom_field_values': create_custom_field_values,
        'create_hr_options': create_hr_options,
        'create_manager_options': create_manager_options,
        'create_client_roles': create_client_roles,
        'create_dynamic_models': create_dynamic_models,
        'create_dynamic_fields_by_model': create_dynamic_fields_by_model,
        'messages': messages,
        **_get_context(request),
    })


def _get_dynamic_models_with_fields(request, include_model_ids=None):
    if not _has_addon(request, 'dynamic_models'):
        return [], {}

    models = []
    fields_by_model = {}
    include_ids = {int(x) for x in (include_model_ids or [])}
    try:
        dm_resp = _api_get(request, '/api/dynamic-models/')
        if dm_resp.status_code == 200:
            dm_data = dm_resp.json()
            all_models = dm_data.get('results', dm_data) if isinstance(dm_data, dict) else dm_data
            models = [
                m for m in all_models
                if m.get('show_in_employee_form') or int(m.get('id') or 0) in include_ids
            ]
            # Attendance is managed via the Attendance module, never from Employee create/edit.
            models = [m for m in models if str(m.get('slug', '')).lower() != 'attendance']
            for model in models:
                model_id = model.get('id')
                f_resp = _api_get(request, f'/api/dynamic-fields/?dynamic_model={model_id}')
                if f_resp.status_code == 200:
                    f_data = f_resp.json()
                    model_fields = (
                        f_data.get('results', f_data) if isinstance(f_data, dict) else f_data
                    )
                    fields_by_model[model_id] = _filter_visible_dynamic_fields(request, model_fields)
                else:
                    fields_by_model[model_id] = []
    except requests.exceptions.ConnectionError:
        return [], {}
    return models, fields_by_model


def _can_manage_all_dynamic_fields(request):
    return request.session.get('role', 'employee') in ('superadmin', 'admin')


def _filter_visible_dynamic_fields(request, fields):
    if _can_manage_all_dynamic_fields(request):
        return fields
    return [field for field in (fields or []) if field.get('visible_to_users', True)]


def _filter_visible_dynamic_record_items(request, fields, record_data):
    if _can_manage_all_dynamic_fields(request):
        return list((record_data or {}).items())
    allowed_keys = {field.get('key') for field in (fields or [])}
    return [
        (key, value)
        for key, value in (record_data or {}).items()
        if key in allowed_keys
    ]


def _save_employee_dynamic_records(request, employee_id, dynamic_models, fields_by_model):
    for model in dynamic_models:
        model_id = model.get('id')
        fields = fields_by_model.get(model_id, [])
        data = {}
        has_value = False

        for field in fields:
            key = field.get('key')
            input_name = f'dm_{model_id}_{key}'
            field_type = field.get('field_type')

            if field_type == 'boolean':
                raw = request.POST.get(input_name)
                if raw in ('true', 'false'):
                    data[key] = raw
                    has_value = True
            elif field_type in ('file', 'image'):
                uploaded = request.FILES.get(input_name)
                if uploaded:
                    data[key] = _store_uploaded_dynamic_file(uploaded, folder=f'dynamic_uploads/model_{model_id}')
                    has_value = True
            else:
                raw = request.POST.get(input_name, '').strip()
                if raw != '':
                    data[key] = raw
                    has_value = True

        if not has_value:
            continue

        existing_resp = _api_get(request, f'/api/dynamic-records/?dynamic_model={model_id}&employee={employee_id}')
        existing_list = []
        if existing_resp.status_code == 200:
            existing_data = existing_resp.json()
            existing_list = (
                existing_data.get('results', existing_data)
                if isinstance(existing_data, dict) else existing_data
            )

        payload = {
            'dynamic_model': model_id,
            'employee': employee_id,
            'data': data,
        }

        if existing_list:
            _api_put(request, f"/api/dynamic-records/{existing_list[0]['id']}/", payload)
        else:
            _api_post(request, '/api/dynamic-records/', payload)


def _employee_error_list(resp, fallback):
    errors = _error_list_from_response(
        resp,
        fallback,
        include_keys=['email', 'first_name', 'last_name', 'role', 'client_role', 'joining_date', 'hr', 'manager'],
    )
    friendly = []
    for msg in errors:
        low = str(msg).lower()
        if 'email:' in low and 'already exists' in low:
            friendly.append('An employee with this email already exists. Please use a different email address.')
        else:
            friendly.append(msg)
    return friendly


def _load_client_roles(request, active_only=True):
    params = {}
    if active_only:
        params['active'] = 'true'
    try:
        resp = _api_get(request, '/api/client-roles/', params=params)
        if resp.status_code != 200:
            return []
        payload = resp.json()
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
    except requests.exceptions.ConnectionError:
        return []

    items = []
    for row in rows:
        items.append({
            'id': str(row.get('id')),
            'name': row.get('name') or '',
            'base_role': str(row.get('base_role') or 'employee').lower(),
            'label': f"{row.get('name') or 'Role'} ({str(row.get('base_role') or 'employee').upper()})",
        })
    return items


def _employee_assignment_options(request, role):
    try:
        resp = _api_get(request, '/api/employees/', params={'role': role})
        if resp.status_code != 200:
            return []
        data = resp.json()
        employees = data.get('results', data) if isinstance(data, dict) else data
    except requests.exceptions.ConnectionError:
        return []

    options = []
    for emp in employees:
        full_name = f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
        label = f"{full_name} ({emp.get('email', '-')})" if full_name else str(emp.get('id'))
        options.append({
            'id': str(emp.get('id')),
            'label': label,
        })
    return options


def _infer_employee_role_from_group_name(group_name):
    name = str(group_name or '').strip().lower()
    if not name:
        return ''
    if 'manager' in name:
        return 'manager'
    if re.search(r'(^|[^a-z])hr([^a-z]|$)', name) or 'human resource' in name:
        return 'hr'
    if 'employee' in name:
        return 'employee'
    return ''


def _infer_client_role_id_from_group_name(group_name, client_roles):
    base_role = _infer_employee_role_from_group_name(group_name)
    if not base_role:
        return ''
    for role_item in client_roles:
        if role_item.get('base_role') == base_role:
            return role_item.get('id') or ''
    return ''


def employee_detail(request, pk):
    permission_redirect = _require_module_permission(request, 'employees.view')
    if permission_redirect:
        return permission_redirect
    messages = _pop_messages(request)
    dynamic_employee_records = []
    attendance_calendar = None
    try:
        resp = _api_get(request, f'/api/employees/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        if resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)

        employee = resp.json()

        dm_resp = _api_get(request, '/api/dynamic-models/')
        if dm_resp.status_code == 200:
            dm_data = dm_resp.json()
            dynamic_models = dm_data.get('results', dm_data) if isinstance(dm_data, dict) else dm_data

            dr_resp = _api_get(request, f'/api/dynamic-records/?employee={pk}')
            records = []
            if dr_resp.status_code == 200:
                dr_data = dr_resp.json()
                records = dr_data.get('results', dr_data) if isinstance(dr_data, dict) else dr_data

            by_model = {r.get('dynamic_model'): r for r in records}
            fields_by_model = {}
            attendance_model = next(
                (m for m in dynamic_models if str(m.get('slug', '')).lower() == 'attendance'),
                None,
            )
            if attendance_model:
                month = request.GET.get('month')
                year = request.GET.get('year')
                today = datetime.date.today()
                try:
                    selected_month = int(month) if month else today.month
                    selected_year = int(year) if year else today.year
                    datetime.date(selected_year, selected_month, 1)
                except ValueError:
                    selected_month = today.month
                    selected_year = today.year

                attendance_records = [
                    r for r in records
                    if r.get('dynamic_model') == attendance_model.get('id')
                ]
                attendance_calendar = _build_attendance_calendar(
                    employee,
                    attendance_records,
                    selected_year,
                    selected_month,
                )

            for model in dynamic_models:
                if str(model.get('slug', '')).lower() == 'attendance':
                    continue
                rec = by_model.get(model.get('id'))
                if rec:
                    model_id = model.get('id')
                    if model_id not in fields_by_model:
                        fields_resp = _api_get(request, f'/api/dynamic-fields/?dynamic_model={model_id}')
                        if fields_resp.status_code == 200:
                            fields_data = fields_resp.json()
                            raw_fields = (
                                fields_data.get('results', fields_data)
                                if isinstance(fields_data, dict) else fields_data
                            )
                            fields_by_model[model_id] = _filter_visible_dynamic_fields(request, raw_fields)
                        else:
                            fields_by_model[model_id] = []
                    visible_items = _filter_visible_dynamic_record_items(
                        request,
                        fields_by_model.get(model_id, []),
                        rec.get('data', {}),
                    )
                    if visible_items:
                        dynamic_employee_records.append({
                            'model': model,
                            'record': rec,
                            'visible_items': visible_items,
                        })
    except requests.exceptions.ConnectionError:
        employee = {}
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'employees/detail.html', {
        'employee': employee,
        'dynamic_employee_records': dynamic_employee_records,
        'attendance_calendar': attendance_calendar,
        'messages': messages,
        **_get_context(request),
    })


def employee_create(request):
    permission_redirect = _require_module_permission(request, 'employees.create')
    if permission_redirect:
        return permission_redirect
    form = EmployeeForm()
    errors = []
    messages = _pop_messages(request)
    custom_fields = []
    custom_field_values = {}
    dynamic_models = []
    dynamic_fields_by_model = {}
    client_roles = _load_client_roles(request)
    role_choices = [(item['id'], item['label']) for item in client_roles]
    hr_options = _employee_assignment_options(request, 'hr')
    manager_options = _employee_assignment_options(request, 'manager')
    form.fields['role'].choices = role_choices

    form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
        (item['id'], item['label']) for item in hr_options
    ]
    form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
        (item['id'], item['label']) for item in manager_options
    ]

    dynamic_models, dynamic_fields_by_model = _get_dynamic_models_with_fields(request)

    if not client_roles:
        errors = ['No roles found. First create at least one role from Role Management, then create employees.']
        return render(request, 'employees/create.html', {
            'form': form,
            'errors': errors,
            'messages': messages,
            'custom_fields': custom_fields,
            'custom_field_values': custom_field_values,
            'hr_options': hr_options,
            'manager_options': manager_options,
            'client_roles': client_roles,
            'dynamic_models': dynamic_models,
            'dynamic_fields_by_model': dynamic_fields_by_model,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        form.fields['role'].choices = role_choices
        form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
            (item['id'], item['label']) for item in hr_options
        ]
        form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
            (item['id'], item['label']) for item in manager_options
        ]
        if form.is_valid():
            try:
                # Get client_id from session (authenticated user's client)
                client_id = request.session.get('client_id')
                
                if not client_id:
                    errors = ['You are not assigned to any client. Contact your administrator.']
                else:
                    employee_data = form.cleaned_data.copy()
                    selected_role = str(employee_data.pop('role', '')).strip()
                    hr_value = employee_data.pop('hr', '')
                    manager_value = employee_data.pop('manager', '')
                    employee_data['client'] = client_id

                    if not selected_role.isdigit():
                        errors = ['Select a valid role.']
                        return render(request, 'employees/create.html', {
                            'form': form,
                            'errors': errors,
                            'messages': messages,
                            'custom_fields': custom_fields,
                            'custom_field_values': custom_field_values,
                            'hr_options': hr_options,
                            'manager_options': manager_options,
                            'client_roles': client_roles,
                            'dynamic_models': dynamic_models,
                            'dynamic_fields_by_model': dynamic_fields_by_model,
                            **_get_context(request),
                        })
                    selected_role_item = next((item for item in client_roles if item['id'] == selected_role), None)
                    employee_data['client_role'] = int(selected_role)
                    employee_data['role'] = (selected_role_item or {}).get('base_role', 'employee')

                    employee_data['hr'] = int(hr_value) if hr_value else None
                    employee_data['manager'] = int(manager_value) if manager_value else None
                    employee_data = _serialize_data(employee_data)
                    
                    # Save employee
                    resp = _api_post(request, '/api/employees/', employee_data)
                    redir = _handle_unauthorized(resp, request)
                    if redir:
                        return redir

                    if resp.status_code == 201:
                        employee = resp.json()
                        employee_id = employee['id']
                        
                        # Save custom field values
                        cf_resp = _api_get(request, '/api/custom-fields/?model_name=Employee')
                        if cf_resp.status_code == 200:
                            cf_data = cf_resp.json()
                            cf_list = cf_data.get('results', cf_data) if isinstance(cf_data, dict) else cf_data
                            
                            for cf in cf_list:
                                field_value = request.POST.get(f'custom_field_{cf["id"]}')
                                if field_value:
                                    cfv_data = {
                                        'employee': employee_id,
                                        'field': cf['id'],
                                        'value': field_value
                                    }
                                    _api_post(request, '/api/custom-field-values/', cfv_data)
                        _save_employee_dynamic_records(
                            request, employee_id, dynamic_models, dynamic_fields_by_model
                        )
                        _flash(request, 'Employee created successfully!', 'success')
                        return redirect('employee_list')
                    else:
                        errors = _employee_error_list(resp, 'Failed to create employee.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    # Fetch custom fields for Employee model
    try:
        cf_resp = _api_get(request, '/api/custom-fields/?model_name=Employee')
        if cf_resp.status_code == 200:
            cf_data = cf_resp.json()
            custom_fields = cf_data.get('results', cf_data) if isinstance(cf_data, dict) else cf_data
    except requests.exceptions.ConnectionError:
        pass

    return render(request, 'employees/create.html', {
        'form': form,
        'errors': errors,
        'messages': messages,
        'custom_fields': custom_fields,
        'custom_field_values': custom_field_values,
        'hr_options': hr_options,
        'manager_options': manager_options,
        'client_roles': client_roles,
        'dynamic_models': dynamic_models,
        'dynamic_fields_by_model': dynamic_fields_by_model,
        **_get_context(request),
    })


def employee_edit(request, pk):
    permission_redirect = _require_module_permission(request, 'employees.edit')
    if permission_redirect:
        return permission_redirect
    errors = []
    messages = _pop_messages(request)
    custom_fields = []
    custom_field_values = {}
    dynamic_models = []
    dynamic_fields_by_model = {}
    dynamic_records_by_model = {}
    client_roles = _load_client_roles(request)
    role_choices = [(item['id'], item['label']) for item in client_roles]
    hr_options = _employee_assignment_options(request, 'hr')
    manager_options = _employee_assignment_options(request, 'manager')
    group_options = []
    account_profile_id = ''
    selected_permission_group = ''
    can_manage_permission_group = request.session.get('role') in ('admin', 'superadmin')

    try:
        get_resp = _api_get(request, f'/api/employees/{pk}/')
        redir = _handle_unauthorized(get_resp, request)
        if redir:
            return redir

        if get_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)

        employee_data = get_resp.json()
        employee_email = str(employee_data.get('email') or '').strip().lower()

        if can_manage_permission_group:
            groups_resp = _api_get(request, '/api/account-groups/')
            redir = _handle_unauthorized(groups_resp, request)
            if redir:
                return redir
            if groups_resp.status_code == 200:
                groups_data = groups_resp.json()
                group_options = (
                    groups_data.get('results', groups_data)
                    if isinstance(groups_data, dict) else groups_data
                )

            accounts_resp = _api_get(request, '/api/accounts/')
            redir = _handle_unauthorized(accounts_resp, request)
            if redir:
                return redir
            if accounts_resp.status_code == 200:
                accounts_data = accounts_resp.json()
                account_rows = (
                    accounts_data.get('results', accounts_data)
                    if isinstance(accounts_data, dict) else accounts_data
                )
                matched_profile = next(
                    (
                        row for row in account_rows
                        if str((row.get('user') or {}).get('email') or '').strip().lower() == employee_email
                    ),
                    None,
                )
                if matched_profile:
                    account_profile_id = str(matched_profile.get('id') or '')
                    selected_permission_group = str(matched_profile.get('permission_group') or '')

        dr_resp = _api_get(request, f'/api/dynamic-records/?employee={pk}')
        if dr_resp.status_code == 200:
            dr_data = dr_resp.json()
            dr_list = dr_data.get('results', dr_data) if isinstance(dr_data, dict) else dr_data
            for rec in dr_list:
                dynamic_records_by_model[rec.get('dynamic_model')] = rec

        dynamic_models, dynamic_fields_by_model = _get_dynamic_models_with_fields(
            request,
            include_model_ids=list(dynamic_records_by_model.keys()),
        )
    except requests.exceptions.ConnectionError:
        return render(request, 'employees/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })

    if request.method == 'POST':
        if can_manage_permission_group:
            selected_permission_group = (request.POST.get('permission_group') or '').strip()
            account_profile_id = (request.POST.get('account_profile_id') or '').strip()
        form = EmployeeForm(request.POST)
        form.fields['role'].choices = role_choices
        form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
            (item['id'], item['label']) for item in hr_options
        ]
        form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
            (item['id'], item['label']) for item in manager_options
        ]
        if form.is_valid():
            try:
                # Get client_id from session (authenticated user's client)
                client_id = request.session.get('client_id')
                
                if not client_id:
                    errors = ['You are not assigned to any client. Contact your administrator.']
                else:
                    emp_update_data = form.cleaned_data.copy()
                    selected_role = str(emp_update_data.pop('role', '')).strip()
                    hr_value = emp_update_data.pop('hr', '')
                    manager_value = emp_update_data.pop('manager', '')
                    if can_manage_permission_group and selected_permission_group:
                        selected_group = next(
                            (g for g in group_options if str(g.get('id')) == str(selected_permission_group)),
                            None,
                        )
                        inferred_role = _infer_employee_role_from_group_name(
                            (selected_group or {}).get('name', '')
                        )
                        if inferred_role:
                            inferred_client_role_id = _infer_client_role_id_from_group_name(
                                (selected_group or {}).get('name', ''),
                                client_roles,
                            )
                            if inferred_client_role_id:
                                selected_role = inferred_client_role_id
                            else:
                                selected_role = inferred_role
                    emp_update_data['client'] = client_id
                    if selected_role.isdigit():
                        selected_role_item = next((item for item in client_roles if item['id'] == selected_role), None)
                        emp_update_data['client_role'] = int(selected_role)
                        emp_update_data['role'] = (selected_role_item or {}).get('base_role', 'employee')
                    else:
                        emp_update_data['role'] = employee_data.get('role') or 'employee'
                        emp_update_data['client_role'] = employee_data.get('client_role')
                    emp_update_data['hr'] = int(hr_value) if hr_value else None
                    emp_update_data['manager'] = int(manager_value) if manager_value else None
                    emp_update_data = _serialize_data(emp_update_data)
                    
                    resp = _api_put(request, f'/api/employees/{pk}/', emp_update_data)
                    redir = _handle_unauthorized(resp, request)
                    if redir:
                        return redir

                    if resp.status_code == 200:
                        # Update custom field values
                        cf_resp = _api_get(request, '/api/custom-fields/?model_name=Employee')
                        if cf_resp.status_code == 200:
                            cf_data = cf_resp.json()
                            cf_list = cf_data.get('results', cf_data) if isinstance(cf_data, dict) else cf_data
                            
                            for cf in cf_list:
                                field_value = request.POST.get(f'custom_field_{cf["id"]}')
                                if field_value:
                                    # Try to update existing value or create new one
                                    cfv_resp = _api_get(request, f'/api/custom-field-values/?employee={pk}&field={cf["id"]}')
                                    if cfv_resp.status_code == 200:
                                        cfv_data = cfv_resp.json()
                                        cfv_list = cfv_data.get('results', cfv_data) if isinstance(cfv_data, dict) else cfv_data
                                        if cfv_list:
                                            cfv_id = cfv_list[0]['id']
                                            _api_put(request, f'/api/custom-field-values/{cfv_id}/', {
                                                'employee': pk,
                                                'field': cf['id'],
                                                'value': field_value
                                            })
                                        else:
                                            _api_post(request, '/api/custom-field-values/', {
                                                'employee': pk,
                                                'field': cf['id'],
                                                'value': field_value
                                            })
                                    else:
                                        _api_post(request, '/api/custom-field-values/', {
                                            'employee': pk,
                                            'field': cf['id'],
                                            'value': field_value
                                        })
                        _save_employee_dynamic_records(
                            request, pk, dynamic_models, dynamic_fields_by_model
                        )

                        if can_manage_permission_group and account_profile_id:
                            assign_payload = {'permission_group': selected_permission_group}
                            assign_resp = _api_post(
                                request,
                                f'/api/accounts/{account_profile_id}/assign-group/',
                                assign_payload,
                            )
                            redir = _handle_unauthorized(assign_resp, request)
                            if redir:
                                return redir
                            if assign_resp.status_code != 200:
                                errors = _error_list_from_response(
                                    assign_resp,
                                    'Employee updated, but failed to update permission group.',
                                )
                                return render(request, 'employees/edit.html', {
                                    'form': form,
                                    'employee': employee_data,
                                    'errors': errors,
                                    'messages': messages,
                                    'custom_fields': custom_fields,
                                    'custom_field_values': custom_field_values,
                                    'hr_options': hr_options,
                                    'manager_options': manager_options,
                                    'client_roles': client_roles,
                                    'group_options': group_options,
                                    'account_profile_id': account_profile_id,
                                    'selected_permission_group': selected_permission_group,
                                    'can_manage_permission_group': can_manage_permission_group,
                                    'dynamic_models': dynamic_models,
                                    'dynamic_fields_by_model': dynamic_fields_by_model,
                                    'dynamic_records_by_model': dynamic_records_by_model,
                                    **_get_context(request),
                                })
                        
                        _flash(request, 'Employee updated successfully!', 'success')
                        return redirect('employee_list')
                    else:
                        errors = _employee_error_list(resp, 'Failed to update employee.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
    else:
        # Pre-fill form with existing data
        initial_data = employee_data.copy()
        initial_data['role'] = str(employee_data.get('client_role') or '')
        initial_data['hr'] = str(employee_data.get('hr') or '')
        initial_data['manager'] = str(employee_data.get('manager') or '')
        form = EmployeeForm(initial=initial_data)
        form.fields['role'].choices = role_choices
        form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
            (item['id'], item['label']) for item in hr_options
        ]
        form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
            (item['id'], item['label']) for item in manager_options
        ]

    # Fetch custom fields for Employee model
    try:
        cf_resp = _api_get(request, '/api/custom-fields/?model_name=Employee')
        if cf_resp.status_code == 200:
            cf_data = cf_resp.json()
            custom_fields = cf_data.get('results', cf_data) if isinstance(cf_data, dict) else cf_data
            
            # Fetch existing values for this employee
            cfv_resp = _api_get(request, f'/api/custom-field-values/?employee={pk}')
            if cfv_resp.status_code == 200:
                cfv_data = cfv_resp.json()
                cfv_list = cfv_data.get('results', cfv_data) if isinstance(cfv_data, dict) else cfv_data
                for cfv in cfv_list:
                    custom_field_values[cfv['field']] = cfv['value']
    except requests.exceptions.ConnectionError:
        pass

    return render(request, 'employees/edit.html', {
        'form': form,
        'employee': employee_data,
        'errors': errors,
        'messages': messages,
        'custom_fields': custom_fields,
        'custom_field_values': custom_field_values,
        'hr_options': hr_options,
        'manager_options': manager_options,
        'client_roles': client_roles,
        'group_options': group_options,
        'account_profile_id': account_profile_id,
        'selected_permission_group': selected_permission_group,
        'can_manage_permission_group': can_manage_permission_group,
        'dynamic_models': dynamic_models,
        'dynamic_fields_by_model': dynamic_fields_by_model,
        'dynamic_records_by_model': dynamic_records_by_model,
        **_get_context(request),
    })


@require_POST
def employee_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'employees.delete')
    if permission_redirect:
        return permission_redirect
    try:
        resp = _api_delete(request, f'/api/employees/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        if resp.status_code == 204:
            _flash(request, 'Employee deleted.', 'success')
        else:
            _flash(request, 'Failed to delete employee.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')

    return redirect('employee_list')


# ─────────────────────────────────────────────────────────────────
# Custom Fields
# ─────────────────────────────────────────────────────────────────

def import_export_page(request):
    permission_redirect = _require_module_permission(request, 'import_export.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'import_export')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    created_count = 0
    failed_rows = []
    client_roles = _load_client_roles(request)

    role_by_id = {str(item.get('id')): item for item in client_roles}
    role_by_name = {
        str(item.get('name') or '').strip().lower(): item
        for item in client_roles
        if str(item.get('name') or '').strip()
    }

    hr_manager_lookup = {}
    try:
        emp_resp = _api_get(request, '/api/employees/')
        if emp_resp.status_code == 200:
            emp_payload = emp_resp.json()
            emp_rows = emp_payload.get('results', emp_payload) if isinstance(emp_payload, dict) else emp_payload
            for emp in emp_rows or []:
                email_key = str(emp.get('email') or '').strip().lower()
                if email_key:
                    hr_manager_lookup[email_key] = emp
    except requests.exceptions.ConnectionError:
        pass

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'export_employees':
            permission_redirect = _require_module_permission(request, 'import_export.export')
            if permission_redirect:
                return permission_redirect
            try:
                export_resp = _api_get(request, '/api/employees/')
                redir = _handle_unauthorized(export_resp, request)
                if redir:
                    return redir
                if export_resp.status_code != 200:
                    errors = _error_list_from_response(export_resp, 'Failed to export employees.')
                else:
                    payload = export_resp.json()
                    rows = payload.get('results', payload) if isinstance(payload, dict) else payload

                    output = io.StringIO()
                    writer = csv.writer(output)
                    writer.writerow([
                        'first_name', 'last_name', 'email', 'role', 'joining_date', 'hr_email', 'manager_email'
                    ])
                    for row in rows or []:
                        writer.writerow([
                            row.get('first_name') or '',
                            row.get('last_name') or '',
                            row.get('email') or '',
                            row.get('client_role_name') or '',
                            row.get('joining_date') or '',
                            row.get('hr_email') or '',
                            row.get('manager_email') or '',
                        ])

                    response = HttpResponse(output.getvalue(), content_type='text/csv')
                    response['Content-Disposition'] = 'attachment; filename="employees_export.csv"'
                    return response
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

        elif action == 'import_employees':
            permission_redirect = _require_module_permission(request, 'import_export.import')
            if permission_redirect:
                return permission_redirect

            upload = request.FILES.get('csv_file')
            if not upload:
                errors = ['Please select a CSV file to import.']
            elif not client_roles:
                errors = ['No roles available. Create at least one role before importing employees.']
            else:
                try:
                    decoded = upload.read().decode('utf-8-sig')
                    reader = csv.DictReader(io.StringIO(decoded))
                    if not reader.fieldnames:
                        errors = ['CSV file is empty or invalid.']
                    else:
                        required_columns = {'first_name', 'last_name', 'email', 'role', 'joining_date'}
                        missing = sorted(list(required_columns - set([str(c).strip() for c in reader.fieldnames])))
                        if missing:
                            errors = [f'Missing required CSV columns: {", ".join(missing)}']
                        else:
                            client_id = request.session.get('client_id')
                            if not client_id:
                                errors = ['No client selected in session. Please login again.']
                            else:
                                for index, row in enumerate(reader, start=2):
                                    first_name = str(row.get('first_name') or '').strip()
                                    last_name = str(row.get('last_name') or '').strip()
                                    email = str(row.get('email') or '').strip()
                                    role_raw = str(row.get('role') or '').strip()
                                    joining_date = str(row.get('joining_date') or '').strip()
                                    hr_email = str(row.get('hr_email') or '').strip().lower()
                                    manager_email = str(row.get('manager_email') or '').strip().lower()

                                    if not first_name or not last_name or not email or not role_raw or not joining_date:
                                        failed_rows.append(f'Row {index}: Required fields are missing.')
                                        continue

                                    selected_role = role_by_id.get(role_raw) or role_by_name.get(role_raw.lower())
                                    if not selected_role:
                                        failed_rows.append(
                                            f'Row {index}: Role "{role_raw}" not found. Use role name or role id from your system.'
                                        )
                                        continue

                                    try:
                                        datetime.date.fromisoformat(joining_date)
                                    except ValueError:
                                        failed_rows.append(
                                            f'Row {index}: joining_date "{joining_date}" must be YYYY-MM-DD.'
                                        )
                                        continue

                                    hr_id = None
                                    manager_id = None
                                    if hr_email:
                                        hr_row = hr_manager_lookup.get(hr_email)
                                        hr_id = hr_row.get('id') if hr_row else None
                                    if manager_email:
                                        manager_row = hr_manager_lookup.get(manager_email)
                                        manager_id = manager_row.get('id') if manager_row else None

                                    payload = {
                                        'first_name': first_name,
                                        'last_name': last_name,
                                        'email': email,
                                        'client': client_id,
                                        'client_role': int(selected_role.get('id')),
                                        'role': selected_role.get('base_role', 'employee'),
                                        'joining_date': joining_date,
                                        'hr': hr_id,
                                        'manager': manager_id,
                                    }

                                    try:
                                        save_resp = _api_post(request, '/api/employees/', payload)
                                        if save_resp.status_code == 201:
                                            created_count += 1
                                        else:
                                            row_errors = _employee_error_list(save_resp, 'Failed to create employee.')
                                            failed_rows.append(f'Row {index}: {"; ".join(row_errors)}')
                                    except requests.exceptions.ConnectionError:
                                        failed_rows.append(f'Row {index}: Backend server unreachable.')

                                if created_count:
                                    _flash(request, f'{created_count} employees imported successfully.', 'success')
                                if failed_rows:
                                    errors = failed_rows[:25]

                except UnicodeDecodeError:
                    errors = ['CSV must be UTF-8 encoded.']

    return render(request, 'import_export/list.html', {
        'messages': messages,
        'errors': errors,
        'created_count': created_count,
        'client_roles': client_roles,
        'sample_headers': ['first_name', 'last_name', 'email', 'role', 'joining_date', 'hr_email', 'manager_email'],
        **_get_context(request),
    })


def leave_type_list(request):
    permission_redirect = _require_module_permission(request, 'leaves.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect
    if request.session.get('role') not in ('superadmin', 'admin'):
        _flash(request, 'Only admin can manage leave types.', 'error')
        return redirect('leave_list')

    messages = _pop_messages(request)
    errors = []
    leave_types = []
    edit_item = None
    search_q = (request.GET.get('q') or '').strip()
    edit_id = (request.GET.get('edit') or '').strip()

    params = {}
    if search_q:
        params['search'] = search_q

    try:
        resp = _api_get(request, '/api/leave-types/', params=params or None)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            leave_types = payload.get('results', payload) if isinstance(payload, dict) else payload
        else:
            errors = _error_list_from_response(resp, 'Failed to load leave types.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if edit_id:
        edit_item = next((row for row in leave_types if str(row.get('id')) == edit_id), None)

    if request.method == 'POST':
        permission_redirect = _require_module_permission(request, 'leaves.create')
        if permission_redirect:
            return permission_redirect
        payload = {
            'name': (request.POST.get('name') or '').strip(),
            'max_days_per_year': (request.POST.get('max_days_per_year') or '').strip() or 0,
            'is_paid': str(request.POST.get('is_paid') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
            'color': (request.POST.get('color') or '').strip(),
        }
        edit_id = (request.POST.get('edit_id') or '').strip()
        try:
            if edit_id:
                save_resp = _api_put(request, f'/api/leave-types/{edit_id}/', payload)
            else:
                save_resp = _api_post(request, '/api/leave-types/', payload)
            redir = _handle_unauthorized(save_resp, request)
            if redir:
                return redir
            if save_resp.status_code in (200, 201):
                _flash(request, 'Leave type saved successfully.', 'success')
                return redirect('leave_type_list')
            errors = _error_list_from_response(save_resp, 'Failed to save leave type.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'leaves/types.html', {
        'leave_types': leave_types,
        'errors': errors,
        'messages': messages,
        'search_q': search_q,
        'edit_item': edit_item,
        **_get_context(request),
    })


@require_POST
def leave_type_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'leaves.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect
    if request.session.get('role') not in ('superadmin', 'admin'):
        _flash(request, 'Only admin can manage leave types.', 'error')
        return redirect('leave_list')
    try:
        resp = _api_delete(request, f'/api/leave-types/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Leave type deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete leave type.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('leave_type_list')


def leave_list(request):
    permission_redirect = _require_module_permission(request, 'leaves.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    leaves = []
    employees = []
    leave_types = []
    selected_status = (request.GET.get('status') or '').strip()
    selected_employee = (request.GET.get('employee') or '').strip()
    current_employee_id = request.session.get('employee_id')
    current_employee_role = (request.session.get('employee_role') or '').strip().lower()
    can_view_all_leaves = (
        request.session.get('role') in ('superadmin', 'admin')
        or current_employee_role in ('hr', 'manager')
    )
    can_create_leave = (
        request.session.get('role') in ('superadmin', 'admin')
        or 'leaves.create' in (request.session.get('module_permissions') or [])
    )
    can_choose_employee = can_view_all_leaves
    show_leave_section = 'list'
    create_form_values = {
        'employee': '',
        'leave_type': '',
        'leave_unit': 'day',
        'half_day_slot': '',
        'leave_hours': '',
        'leave_start_time': '',
        'leave_end_time': '',
        'start_date': '',
        'end_date': '',
        'reason': '',
    }

    params = {}
    if selected_status:
        params['status'] = selected_status
    if can_view_all_leaves and selected_employee:
        params['employee'] = selected_employee
    elif not can_view_all_leaves and current_employee_id:
        params['employee'] = str(current_employee_id)

    try:
        leaves_resp = _api_get(request, '/api/leaves/', params=params or None)
        redir = _handle_unauthorized(leaves_resp, request)
        if redir:
            return redir
        if leaves_resp.status_code == 200:
            leave_data = leaves_resp.json()
            leaves = leave_data.get('results', leave_data) if isinstance(leave_data, dict) else leave_data
        else:
            errors = _error_list_from_response(leaves_resp, 'Failed to load leave requests.')

        if can_view_all_leaves:
            employees_resp = _api_get(request, '/api/employees/')
            redir = _handle_unauthorized(employees_resp, request)
            if redir:
                return redir
            if employees_resp.status_code == 200:
                emp_data = employees_resp.json()
                employees = emp_data.get('results', emp_data) if isinstance(emp_data, dict) else emp_data

        leave_type_resp = _api_get(request, '/api/leave-types/')
        redir = _handle_unauthorized(leave_type_resp, request)
        if redir:
            return redir
        if leave_type_resp.status_code == 200:
            leave_type_data = leave_type_resp.json()
            leave_types = leave_type_data.get('results', leave_type_data) if isinstance(leave_type_data, dict) else leave_type_data
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    leave_type_map = {str(row.get('name', '')).lower(): row for row in leave_types}
    for leave in leaves:
        leave_type = leave_type_map.get(str(leave.get('leave_type', '')).lower())
        leave['leave_type_is_paid'] = leave_type.get('is_paid') if leave_type else leave.get('leave_type_is_paid')
    pending_count = len([row for row in leaves if str(row.get('status', '')).lower() == 'pending'])

    if request.method == 'POST' and request.POST.get('action') == 'create_leave':
        show_leave_section = 'create'
        permission_redirect = _require_module_permission(request, 'leaves.create')
        if permission_redirect:
            return permission_redirect

        create_form_values = {
            'employee': (request.POST.get('employee') or '').strip(),
            'leave_type': (request.POST.get('leave_type') or '').strip(),
            'leave_unit': (request.POST.get('leave_unit') or 'day').strip(),
            'half_day_slot': (request.POST.get('half_day_slot') or '').strip(),
            'leave_hours': (request.POST.get('leave_hours') or '').strip(),
            'leave_start_time': (request.POST.get('leave_start_time') or '').strip(),
            'leave_end_time': (request.POST.get('leave_end_time') or '').strip(),
            'start_date': (request.POST.get('start_date') or '').strip(),
            'end_date': (request.POST.get('end_date') or '').strip(),
            'reason': (request.POST.get('reason') or '').strip(),
        }

        employee_id = (
            str(current_employee_id)
            if (not can_choose_employee and current_employee_id)
            else create_form_values['employee']
        )
        payload = {
            'employee': employee_id,
            'leave_type': create_form_values['leave_type'],
            'leave_unit': create_form_values['leave_unit'] or 'day',
            'half_day_slot': create_form_values['half_day_slot'] or '',
            'leave_hours': create_form_values['leave_hours'] or None,
            'leave_start_time': create_form_values['leave_start_time'] or None,
            'leave_end_time': create_form_values['leave_end_time'] or None,
            'start_date': create_form_values['start_date'],
            'end_date': create_form_values['end_date'],
            'reason': create_form_values['reason'],
        }
        try:
            resp = _api_post(request, '/api/leaves/', payload)
            redir = _handle_unauthorized(resp, request)
            if redir:
                return redir
            if resp.status_code == 201:
                _flash(request, 'Leave request created successfully.', 'success')
                return redirect('leave_list')
            errors = _error_list_from_response(resp, 'Failed to create leave request.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'leaves/list.html', {
        'leaves': leaves,
        'employees': employees,
        'leave_types': leave_types,
        'errors': errors,
        'messages': messages,
        'selected_status': selected_status,
        'selected_employee': selected_employee,
        'pending_count': pending_count,
        'can_create_leave': can_create_leave,
        'can_view_all_leaves': can_view_all_leaves,
        'can_choose_employee': can_choose_employee,
        'show_leave_section': show_leave_section,
        'create_form_values': create_form_values,
        **_get_context(request),
    })


def leave_create(request):
    permission_redirect = _require_module_permission(request, 'leaves.create')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    employees = []
    leave_types = []
    current_employee_id = request.session.get('employee_id')
    current_employee_role = (request.session.get('employee_role') or '').strip().lower()
    can_choose_employee = (
        request.session.get('role') in ('superadmin', 'admin')
        or current_employee_role in ('hr', 'manager')
    )

    try:
        employees_resp = _api_get(request, '/api/employees/')
        redir = _handle_unauthorized(employees_resp, request)
        if redir:
            return redir
        if employees_resp.status_code == 200:
            emp_data = employees_resp.json()
            employees_rows = emp_data.get('results', emp_data) if isinstance(emp_data, dict) else emp_data
            if can_choose_employee:
                employees = employees_rows
            elif current_employee_id:
                employees = [row for row in employees_rows if str(row.get('id')) == str(current_employee_id)]

        leave_type_resp = _api_get(request, '/api/leave-types/')
        redir = _handle_unauthorized(leave_type_resp, request)
        if redir:
            return redir
        if leave_type_resp.status_code == 200:
            leave_type_data = leave_type_resp.json()
            leave_types = leave_type_data.get('results', leave_type_data) if isinstance(leave_type_data, dict) else leave_type_data
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if request.method == 'POST':
        employee_id = (
            str(current_employee_id)
            if (not can_choose_employee and current_employee_id)
            else (request.POST.get('employee') or '').strip()
        )
        payload = {
            'employee': employee_id,
            'leave_type': (request.POST.get('leave_type') or '').strip(),
            'leave_unit': (request.POST.get('leave_unit') or 'day').strip(),
            'half_day_slot': (request.POST.get('half_day_slot') or '').strip(),
            'leave_hours': (request.POST.get('leave_hours') or '').strip() or None,
            'leave_start_time': (request.POST.get('leave_start_time') or '').strip() or None,
            'leave_end_time': (request.POST.get('leave_end_time') or '').strip() or None,
            'start_date': (request.POST.get('start_date') or '').strip(),
            'end_date': (request.POST.get('end_date') or '').strip(),
            'reason': (request.POST.get('reason') or '').strip(),
        }
        try:
            resp = _api_post(request, '/api/leaves/', payload)
            redir = _handle_unauthorized(resp, request)
            if redir:
                return redir
            if resp.status_code == 201:
                _flash(request, 'Leave request created successfully.', 'success')
                return redirect('leave_list')
            errors = _error_list_from_response(resp, 'Failed to create leave request.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'leaves/create.html', {
        'employees': employees,
        'leave_types': leave_types,
        'errors': errors,
        'messages': messages,
        'can_choose_employee': can_choose_employee,
        **_get_context(request),
    })


@require_POST
def leave_review(request, pk):
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect

    payload = {
        'status': (request.POST.get('status') or '').strip().lower(),
        'reviewer_comment': (request.POST.get('reviewer_comment') or '').strip(),
    }
    try:
        resp = _api_post(request, f'/api/leaves/{pk}/review/', payload)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            _flash(request, 'Leave request updated.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to review leave request.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('leave_list')


@require_POST
def leave_cancel(request, pk):
    permission_redirect = _require_module_permission(request, 'leaves.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect

    payload = {'reviewer_comment': (request.POST.get('reviewer_comment') or '').strip()}
    try:
        resp = _api_post(request, f'/api/leaves/{pk}/cancel/', payload)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            _flash(request, 'Leave request cancelled.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to cancel leave request.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('leave_list')


@require_POST
def leave_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'leaves.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/leaves/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Leave request deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete leave request.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('leave_list')


def leave_balance(request):
    permission_redirect = _require_module_permission(request, 'leaves.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'leave_management')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    balances = []
    try:
        resp = _api_get(request, '/api/leave-balance/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            balances = payload.get('results', payload) if isinstance(payload, dict) else payload
            normalized_rows = []
            for row in balances or []:
                row_balances = row.get('balances', []) if isinstance(row, dict) else []
                normalized_balances = []
                for bal in row_balances:
                    if not isinstance(bal, dict):
                        continue
                    total_value = bal.get('total', bal.get('total_days', 0))
                    used_value = bal.get('used', bal.get('used_days', bal.get('consumed', 0)))
                    available_value = bal.get(
                        'available',
                        bal.get('remaining', bal.get('remaining_days', total_value)),
                    )
                    normalized_balances.append({
                        **bal,
                        'total': total_value,
                        'used': used_value,
                        'available': available_value,
                    })
                normalized_rows.append({
                    **row,
                    'balances': normalized_balances,
                } if isinstance(row, dict) else row)
            balances = normalized_rows
        else:
            errors = _error_list_from_response(resp, 'Failed to load leave balances.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    return render(request, 'leaves/balance.html', {
        'balances': balances,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


def holiday_list(request):
    permission_redirect = _require_module_permission(request, 'holidays.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'holidays')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    holidays = []
    edit_item = None
    search_q = (request.GET.get('q') or '').strip()
    selected_paid = (request.GET.get('is_paid') or '').strip().lower()
    edit_id = (request.GET.get('edit') or '').strip()

    params = {}
    if search_q:
        params['search'] = search_q
    if selected_paid in ('true', 'false'):
        params['is_paid'] = selected_paid

    try:
        resp = _api_get(request, '/api/holidays/', params=params or None)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            holidays = payload.get('results', payload) if isinstance(payload, dict) else payload
        else:
            errors = _error_list_from_response(resp, 'Failed to load holidays.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if edit_id:
        edit_item = next((row for row in holidays if str(row.get('id')) == edit_id), None)

    if request.method == 'POST':
        edit_id = (request.POST.get('edit_id') or '').strip()
        permission_key = 'holidays.edit' if edit_id else 'holidays.create'
        permission_redirect = _require_module_permission(request, permission_key)
        if permission_redirect:
            return permission_redirect

        payload = {
            'name': (request.POST.get('name') or '').strip(),
            'holiday_type': (request.POST.get('holiday_type') or '').strip(),
            'start_date': (request.POST.get('start_date') or '').strip(),
            'end_date': (request.POST.get('end_date') or '').strip(),
            'is_paid': str(request.POST.get('is_paid') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
            'description': (request.POST.get('description') or '').strip(),
            'is_active': str(request.POST.get('is_active') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
        }
        try:
            if edit_id:
                save_resp = _api_put(request, f'/api/holidays/{edit_id}/', payload)
            else:
                save_resp = _api_post(request, '/api/holidays/', payload)
            redir = _handle_unauthorized(save_resp, request)
            if redir:
                return redir
            if save_resp.status_code in (200, 201):
                _flash(request, 'Holiday saved successfully.', 'success')
                return redirect('holiday_list')
            errors = _error_list_from_response(save_resp, 'Failed to save holiday.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'holidays/list.html', {
        'holidays': holidays,
        'errors': errors,
        'messages': messages,
        'search_q': search_q,
        'selected_paid': selected_paid,
        'edit_item': edit_item,
        **_get_context(request),
    })


@require_POST
def holiday_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'holidays.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'holidays')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/holidays/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Holiday deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete holiday.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('holiday_list')


def shift_list(request):
    permission_redirect = _require_module_permission(request, 'shifts.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'shift_management')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    shifts = []
    edit_item = None
    search_q = (request.GET.get('q') or '').strip()
    selected_active = (request.GET.get('is_active') or '').strip().lower()
    edit_id = (request.GET.get('edit') or '').strip()

    params = {}
    if search_q:
        params['search'] = search_q
    if selected_active in ('true', 'false'):
        params['is_active'] = selected_active

    try:
        resp = _api_get(request, '/api/shifts/', params=params or None)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            shifts = payload.get('results', payload) if isinstance(payload, dict) else payload
        else:
            errors = _error_list_from_response(resp, 'Failed to load shifts.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if edit_id:
        edit_item = next((row for row in shifts if str(row.get('id')) == edit_id), None)

    if request.method == 'POST':
        edit_id = (request.POST.get('edit_id') or '').strip()
        permission_key = 'shifts.edit' if edit_id else 'shifts.create'
        permission_redirect = _require_module_permission(request, permission_key)
        if permission_redirect:
            return permission_redirect

        payload = {
            'name': (request.POST.get('name') or '').strip(),
            'code': (request.POST.get('code') or '').strip(),
            'start_time': (request.POST.get('start_time') or '').strip(),
            'end_time': (request.POST.get('end_time') or '').strip(),
            'grace_minutes': int((request.POST.get('grace_minutes') or '0').strip() or 0),
            'is_night_shift': str(request.POST.get('is_night_shift') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
            'weekly_off': (request.POST.get('weekly_off') or '').strip(),
            'is_active': str(request.POST.get('is_active') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
        }
        try:
            if edit_id:
                save_resp = _api_put(request, f'/api/shifts/{edit_id}/', payload)
            else:
                save_resp = _api_post(request, '/api/shifts/', payload)
            redir = _handle_unauthorized(save_resp, request)
            if redir:
                return redir
            if save_resp.status_code in (200, 201):
                _flash(request, 'Shift saved successfully.', 'success')
                return redirect('shift_list')
            errors = _error_list_from_response(save_resp, 'Failed to save shift.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'shifts/list.html', {
        'shifts': shifts,
        'errors': errors,
        'messages': messages,
        'search_q': search_q,
        'selected_active': selected_active,
        'edit_item': edit_item,
        **_get_context(request),
    })


@require_POST
def shift_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'shifts.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'shift_management')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/shifts/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Shift deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete shift.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('shift_list')


def bank_list(request):
    permission_redirect = _require_module_permission(request, 'bank.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'bank_management')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    bank_accounts = []
    employees = []
    edit_item = None
    search_q = (request.GET.get('q') or '').strip()
    selected_employee = (request.GET.get('employee') or '').strip()
    edit_id = (request.GET.get('edit') or '').strip()

    params = {}
    if search_q:
        params['search'] = search_q
    if selected_employee:
        params['employee'] = selected_employee

    try:
        emp_resp = _api_get(request, '/api/employees/')
        redir = _handle_unauthorized(emp_resp, request)
        if redir:
            return redir
        if emp_resp.status_code == 200:
            emp_payload = emp_resp.json()
            employees = emp_payload.get('results', emp_payload) if isinstance(emp_payload, dict) else emp_payload

        resp = _api_get(request, '/api/bank-accounts/', params=params or None)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            bank_accounts = payload.get('results', payload) if isinstance(payload, dict) else payload
        else:
            errors = _error_list_from_response(resp, 'Failed to load bank accounts.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    if edit_id:
        edit_item = next((row for row in bank_accounts if str(row.get('id')) == edit_id), None)

    if request.method == 'POST':
        edit_id = (request.POST.get('edit_id') or '').strip()
        permission_key = 'bank.edit' if edit_id else 'bank.create'
        permission_redirect = _require_module_permission(request, permission_key)
        if permission_redirect:
            return permission_redirect

        payload = {
            'employee': (request.POST.get('employee') or '').strip() or None,
            'bank_name': (request.POST.get('bank_name') or '').strip(),
            'account_holder_name': (request.POST.get('account_holder_name') or '').strip(),
            'account_number': (request.POST.get('account_number') or '').strip(),
            'ifsc_code': (request.POST.get('ifsc_code') or '').strip(),
            'branch_name': (request.POST.get('branch_name') or '').strip(),
            'upi_id': (request.POST.get('upi_id') or '').strip(),
            'is_primary': str(request.POST.get('is_primary') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
            'is_active': str(request.POST.get('is_active') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
        }
        if payload['employee'] is None:
            errors = ['Employee is required.']
        else:
            try:
                payload['employee'] = int(payload['employee'])
                if edit_id:
                    save_resp = _api_put(request, f'/api/bank-accounts/{edit_id}/', payload)
                else:
                    save_resp = _api_post(request, '/api/bank-accounts/', payload)
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code in (200, 201):
                    _flash(request, 'Bank account saved successfully.', 'success')
                    return redirect('bank_list')
                errors = _error_list_from_response(save_resp, 'Failed to save bank account.')
            except ValueError:
                errors = ['Invalid employee id.']
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'banks/list.html', {
        'bank_accounts': bank_accounts,
        'employees': employees,
        'errors': errors,
        'messages': messages,
        'search_q': search_q,
        'selected_employee': selected_employee,
        'edit_item': edit_item,
        **_get_context(request),
    })


@require_POST
def bank_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'bank.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'bank_management')
    if addon_redirect:
        return addon_redirect

    try:
        resp = _api_delete(request, f'/api/bank-accounts/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Bank account deleted.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(resp, 'Failed to delete bank account.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('bank_list')


def payroll_list(request):
    addon_redirect = _require_addon(request, 'payroll')
    if addon_redirect:
        return addon_redirect

    messages = _pop_messages(request)
    errors = []
    role = request.session.get('role', 'employee')
    can_manage_payroll = role in ('superadmin', 'admin')

    today = datetime.date.today()
    selected_year = request.GET.get('year') or str(today.year)
    selected_month = request.GET.get('month') or str(today.month)
    selected_employee = (request.GET.get('employee') or '').strip()

    params = {'year': selected_year, 'month': selected_month}
    if selected_employee:
        params['employee'] = selected_employee

    employees = []
    rows = []
    policy_row = None
    compensation_by_employee = {}

    if request.method == 'POST' and can_manage_payroll:
        form_action = (request.POST.get('form_action') or '').strip()
        try:
            if form_action == 'save_policy':
                payload = {
                    'monthly_working_days': int((request.POST.get('monthly_working_days') or '24').strip() or 24),
                    'standard_hours_per_day': (request.POST.get('standard_hours_per_day') or '8').strip() or '8',
                    'salary_basis': (request.POST.get('salary_basis') or 'day').strip() or 'day',
                    'allow_extra_hours_payout': str(request.POST.get('allow_extra_hours_payout') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
                    'allow_extra_days_payout': str(request.POST.get('allow_extra_days_payout') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
                }
                policy_id = (request.POST.get('policy_id') or '').strip()
                if policy_id:
                    save_resp = _api_put(request, f'/api/payroll-policy/{policy_id}/', payload)
                else:
                    save_resp = _api_post(request, '/api/payroll-policy/', payload)
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code in (200, 201):
                    _flash(request, 'Payroll policy saved successfully.', 'success')
                    return redirect('payroll_list')
                errors = _error_list_from_response(save_resp, 'Failed to save payroll policy.')

            elif form_action == 'save_compensation':
                employee_id = (request.POST.get('employee_id') or '').strip()
                salary_basis = (request.POST.get('comp_salary_basis') or 'monthly').strip() or 'monthly'
                monthly_salary_raw = (request.POST.get('monthly_salary') or '').strip()
                daily_salary_raw = (request.POST.get('daily_salary') or '').strip()
                hourly_salary_raw = (request.POST.get('hourly_salary') or '').strip()
                payload = {
                    'employee': employee_id,
                    'salary_basis': salary_basis,
                    'monthly_salary': float(monthly_salary_raw) if monthly_salary_raw else None,
                    'daily_salary': float(daily_salary_raw) if daily_salary_raw else None,
                    'hourly_salary': float(hourly_salary_raw) if hourly_salary_raw else None,
                    'effective_from': (request.POST.get('effective_from') or '').strip() or None,
                }
                compensation_id = (request.POST.get('compensation_id') or '').strip()
                if compensation_id:
                    save_resp = _api_put(request, f'/api/employee-compensation/{compensation_id}/', payload)
                else:
                    save_resp = _api_post(request, '/api/employee-compensation/', payload)
                redir = _handle_unauthorized(save_resp, request)
                if redir:
                    return redir
                if save_resp.status_code in (200, 201):
                    _flash(request, 'Employee salary details saved successfully.', 'success')
                    return redirect('payroll_list')
                errors = _error_list_from_response(save_resp, 'Failed to save employee salary details.')
        except (TypeError, ValueError):
            errors = ['Please enter valid numeric values for salary and policy fields.']
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    try:
        # Keep payroll policy aligned with onboarding setup so report uses selected
        # payable-days mode and default shift hours for the chosen month.
        if can_manage_payroll:
            app_settings = request.session.get('app_settings')
            derived_policy = _derive_policy_from_onboarding(app_settings, selected_year, selected_month)
            if derived_policy:
                sync_policy_resp = _api_get(request, '/api/payroll-policy/')
                redir = _handle_unauthorized(sync_policy_resp, request)
                if redir:
                    return redir
                if sync_policy_resp.status_code == 200:
                    sync_payload = sync_policy_resp.json()
                    sync_rows = (
                        sync_payload.get('results', sync_payload)
                        if isinstance(sync_payload, dict) else sync_payload
                    )
                    existing_policy = sync_rows[0] if sync_rows else None
                    if existing_policy:
                        needs_update = any(
                            str(existing_policy.get(k)) != str(v)
                            for k, v in derived_policy.items()
                        )
                        if needs_update:
                            _api_put(request, f"/api/payroll-policy/{existing_policy.get('id')}/", derived_policy)
                    else:
                        _api_post(request, '/api/payroll-policy/', derived_policy)

        if can_manage_payroll:
            emp_resp = _api_get(request, '/api/employees/')
            redir = _handle_unauthorized(emp_resp, request)
            if redir:
                return redir
            if emp_resp.status_code == 200:
                payload = emp_resp.json()
                employees = payload.get('results', payload) if isinstance(payload, dict) else payload

            compensation_resp = _api_get(request, '/api/employee-compensation/')
            redir = _handle_unauthorized(compensation_resp, request)
            if redir:
                return redir
            if compensation_resp.status_code == 200:
                payload = compensation_resp.json()
                compensation_rows = payload.get('results', payload) if isinstance(payload, dict) else payload
                for row in compensation_rows:
                    emp_id = row.get('employee')
                    if emp_id is not None:
                        compensation_by_employee[str(emp_id)] = row

        policy_resp = _api_get(request, '/api/payroll-policy/')
        redir = _handle_unauthorized(policy_resp, request)
        if redir:
            return redir
        if policy_resp.status_code == 200:
            payload = policy_resp.json()
            policy_list = payload.get('results', payload) if isinstance(payload, dict) else payload
            policy_row = policy_list[0] if policy_list else None

        report_resp = _api_get(request, '/api/payroll-report/', params=params)
        redir = _handle_unauthorized(report_resp, request)
        if redir:
            return redir
        if report_resp.status_code == 200:
            payload = report_resp.json()
            rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        else:
            errors = _error_list_from_response(report_resp, 'Failed to load payroll report.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    month_options = [(i, calendar.month_name[i]) for i in range(1, 13)]
    year_options = [today.year - 1, today.year, today.year + 1]

    return render(request, 'payroll/list.html', {
        'messages': messages,
        'errors': errors,
        'rows': rows,
        'employees': employees,
        'policy_row': policy_row,
        'compensation_by_employee': compensation_by_employee,
        'compensation_by_employee_json': json.dumps(compensation_by_employee),
        'can_manage_payroll': can_manage_payroll,
        'selected_year': str(selected_year),
        'selected_month': str(selected_month),
        'selected_employee': selected_employee,
        'month_options': month_options,
        'year_options': year_options,
        **_get_context(request),
    })


def activity_log_list(request):
    permission_redirect = _require_module_permission(request, 'activity_logs.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'activity_logs')
    if addon_redirect:
        return addon_redirect

    role = request.session.get('role', 'employee')
    employee_role = (request.session.get('employee_role') or '').strip().lower()
    if role == 'employee' and employee_role not in ('hr', 'manager'):
        return render(request, 'errors/403.html', status=403)

    messages = _pop_messages(request)
    errors = []
    logs = []

    action_filter = (request.GET.get('action') or '').strip().lower()
    module_filter = (request.GET.get('module') or '').strip()
    user_filter = (request.GET.get('user') or '').strip()
    search_q = (request.GET.get('q') or '').strip()

    params = {}
    if action_filter:
        params['action'] = action_filter
    if module_filter:
        params['module'] = module_filter
    if search_q:
        params['search'] = search_q

    try:
        resp = _api_get(request, '/api/activity-logs/', params=params or None)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 200:
            payload = resp.json()
            logs = payload.get('results', payload) if isinstance(payload, dict) else payload
            for row in logs or []:
                raw_created_at = str(row.get('created_at') or '').strip()
                display_created_at = raw_created_at
                if raw_created_at:
                    try:
                        parsed_dt = datetime.datetime.fromisoformat(raw_created_at.replace('Z', '+00:00'))
                        if parsed_dt.tzinfo is not None:
                            parsed_dt = timezone.localtime(parsed_dt)
                        display_created_at = parsed_dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        display_created_at = raw_created_at
                row['created_at_display'] = display_created_at
        else:
            errors = _error_list_from_response(resp, 'Failed to load activity logs.')
    except requests.exceptions.ConnectionError:
        errors = ['Backend server unreachable.']

    module_options = sorted({str(row.get('module') or '') for row in logs if str(row.get('module') or '').strip()})
    user_options = sorted({str(row.get('actor_username') or '') for row in logs if str(row.get('actor_username') or '').strip()}, key=lambda s: s.lower())
    if user_filter:
        user_filter_lower = user_filter.lower()
        logs = [
            row for row in logs
            if str(row.get('actor_username') or '').strip().lower() == user_filter_lower
        ]

    return render(request, 'activity_logs/list.html', {
        'messages': messages,
        'errors': errors,
        'logs': logs,
        'action_filter': action_filter,
        'module_filter': module_filter,
        'module_options': module_options,
        'user_filter': user_filter,
        'user_options': user_options,
        'search_q': search_q,
        **_get_context(request),
    })


def custom_field_list(request):
    permission_redirect = _require_module_permission(request, 'custom_fields.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'custom_fields')
    if addon_redirect:
        return addon_redirect
    messages = _pop_messages(request)
    role = request.session.get('role', 'employee')
    show_client_model = role == 'superadmin'

    try:
        path = '/api/custom-fields/' if show_client_model else '/api/custom-fields/?model_name=Employee'
        resp = _api_get(request, path)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        data = resp.json() if resp.status_code == 200 else []
        custom_fields = data.get('results', data) if isinstance(data, dict) else data
    except requests.exceptions.ConnectionError:
        custom_fields = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'custom_fields/list.html', {
        'custom_fields': custom_fields,
        'messages': messages,
        'username': request.session.get('username', ''),
        'role': role,
        'show_client_model': show_client_model,
    })


def custom_field_create(request):
    permission_redirect = _require_module_permission(request, 'custom_fields.create')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'custom_fields')
    if addon_redirect:
        return addon_redirect
    form = CustomFieldForm()
    errors = []
    messages = _pop_messages(request)
    role = request.session.get('role', 'employee')
    show_client_model = role == 'superadmin'
    form.fields['model_name'].choices = (
        [('Employee', 'Employee'), ('Client', 'Client')]
        if show_client_model else
        [('Employee', 'Employee')]
    )

    if request.method == 'POST':
        form = CustomFieldForm(request.POST)
        form.fields['model_name'].choices = (
            [('Employee', 'Employee'), ('Client', 'Client')]
            if show_client_model else
            [('Employee', 'Employee')]
        )
        if form.is_valid():
            try:
                # Get client_id from session (authenticated user's client)
                client_id = request.session.get('client_id')
                
                if not client_id:
                    errors = ['You are not assigned to any client. Contact your administrator.']
                else:
                    data = form.cleaned_data.copy()
                    if not show_client_model and data.get('model_name') == 'Client':
                        errors = ['Only superadmin can create Client custom fields.']
                        return render(request, 'custom_fields/create.html', {
                            'form': form,
                            'errors': errors,
                            'messages': messages,
                            'username': request.session.get('username', ''),
                            'role': role,
                            'show_client_model': show_client_model,
                        })
                    data['client'] = client_id
                    
                    resp = _api_post(request, '/api/custom-fields/', data)
                    redir = _handle_unauthorized(resp, request)
                    if redir:
                        return redir

                    if resp.status_code == 201:
                        _flash(request, 'Custom field created successfully!', 'success')
                        return redirect('custom_field_list')
                    else:
                        errors = [f'{k}: {v}' for k, v in resp.json().items()]
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'custom_fields/create.html', {
        'form': form,
        'errors': errors,
        'messages': messages,
        'username': request.session.get('username', ''),
        'role': role,
        'show_client_model': show_client_model,
    })


def custom_field_edit(request, pk):
    permission_redirect = _require_module_permission(request, 'custom_fields.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'custom_fields')
    if addon_redirect:
        return addon_redirect
    errors = []
    messages = _pop_messages(request)
    role = request.session.get('role', 'employee')
    show_client_model = role == 'superadmin'

    try:
        get_resp = _api_get(request, f'/api/custom-fields/{pk}/')
        redir = _handle_unauthorized(get_resp, request)
        if redir:
            return redir

        if get_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)

        cf_data = get_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'custom_fields/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            'username': request.session.get('username', ''),
        })

    if request.method == 'POST':
        form = CustomFieldForm(request.POST)
        form.fields['model_name'].choices = (
            [('Employee', 'Employee'), ('Client', 'Client')]
            if show_client_model else
            [('Employee', 'Employee')]
        )
        if form.is_valid():
            try:
                data = form.cleaned_data.copy()
                if not show_client_model and data.get('model_name') == 'Client':
                    errors = ['Only superadmin can update Client custom fields.']
                    return render(request, 'custom_fields/edit.html', {
                        'form': form,
                        'custom_field': cf_data,
                        'errors': errors,
                        'messages': messages,
                        'username': request.session.get('username', ''),
                        'role': role,
                        'show_client_model': show_client_model,
                    })

                client_id = request.session.get('client_id') or cf_data.get('client')
                if not client_id:
                    errors = ['Client context not found for this user.']
                else:
                    data['client'] = client_id
                    resp = _api_put(request, f'/api/custom-fields/{pk}/', data)
                    redir = _handle_unauthorized(resp, request)
                    if redir:
                        return redir

                    if resp.status_code == 200:
                        _flash(request, 'Custom field updated successfully!', 'success')
                        return redirect('custom_field_list')
                    else:
                        errors = [f'{k}: {v}' for k, v in resp.json().items()]
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
    else:
        form = CustomFieldForm(initial=cf_data)
        form.fields['model_name'].choices = (
            [('Employee', 'Employee'), ('Client', 'Client')]
            if show_client_model else
            [('Employee', 'Employee')]
        )

    return render(request, 'custom_fields/edit.html', {
        'form': form,
        'custom_field': cf_data,
        'errors': errors,
        'messages': messages,
        'username': request.session.get('username', ''),
        'role': role,
        'show_client_model': show_client_model,
    })


@require_POST
def custom_field_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'custom_fields.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'custom_fields')
    if addon_redirect:
        return addon_redirect
    try:
        resp = _api_delete(request, f'/api/custom-fields/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir

        if resp.status_code == 204:
            _flash(request, 'Custom field deleted.', 'success')
        else:
            _flash(request, 'Failed to delete custom field.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')

    return redirect('custom_field_list')


# Dynamic Models
def _error_list_from_response(resp, fallback, include_keys=None, max_items=3):
    if not resp.content:
        return [fallback]
    try:
        payload = resp.json()
    except ValueError:
        return [fallback]

    if isinstance(payload, dict):
        if include_keys:
            items = [(k, payload.get(k)) for k in include_keys if k in payload]
            if not items:
                items = list(payload.items())
        else:
            items = list(payload.items())

        messages = []
        for key, value in items[:max_items]:
            if isinstance(value, list):
                value_text = ', '.join(str(v) for v in value[:2])
            elif isinstance(value, dict):
                nested_keys = list(value.keys())
                preview = ', '.join(str(k) for k in nested_keys[:3])
                if len(nested_keys) > 3:
                    preview = f'{preview}, ...'
                value_text = f'{{{preview}}}'
            else:
                value_text = str(value)
            messages.append(f'{key}: {value_text}')

        remaining = len(items) - len(messages)
        if remaining > 0:
            messages.append(f'...and {remaining} more fields.')

        return messages if messages else [fallback]

    return [fallback]


def dynamic_model_list(request):
    permission_redirect = _require_module_permission(request, 'dynamic_models.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    messages = _pop_messages(request)
    role = request.session.get('role', 'employee')
    clients = []
    client_name_map = {}

    try:
        resp = _api_get(request, '/api/dynamic-models/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        data = resp.json() if resp.status_code == 200 else []
        dynamic_models = data.get('results', data) if isinstance(data, dict) else data

        if role == 'superadmin':
            client_resp = _api_get(request, '/api/clients/')
            redir = _handle_unauthorized(client_resp, request)
            if redir:
                return redir
            if client_resp.status_code == 200:
                client_payload = client_resp.json()
                clients = client_payload.get('results', client_payload) if isinstance(client_payload, dict) else client_payload
                client_name_map = {
                    str(c.get('id')): str(c.get('name') or '')
                    for c in clients
                }
    except requests.exceptions.ConnectionError:
        dynamic_models = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    if role == 'superadmin':
        for model in dynamic_models:
            model['client_name'] = client_name_map.get(str(model.get('client')), str(model.get('client') or '-'))

    return render(request, 'dynamic_models/list.html', {
        'dynamic_models': dynamic_models,
        'clients': clients,
        'messages': messages,
        'role': role,
        **_get_context(request),
    })


def dynamic_model_create(request):
    permission_redirect = _require_module_permission(request, 'dynamic_models.create')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    form = DynamicModelForm()
    errors = []
    messages = _pop_messages(request)
    role = request.session.get('role', 'employee')
    is_superadmin = role == 'superadmin'

    if request.method == 'POST':
        form = DynamicModelForm(request.POST)
        if form.is_valid():
            payload = {
                'name': form.cleaned_data['name'],
                'slug': form.cleaned_data['slug'],
                'show_in_employee_form': bool(form.cleaned_data.get('show_in_employee_form')),
            }
            if is_superadmin:
                client_id = request.POST.get('client')
                if not client_id:
                    errors = ['Client id is required for superadmin.']
                    return render(request, 'dynamic_models/create.html', {
                        'form': form,
                        'errors': errors,
                        'messages': messages,
                        'role': role,
                        **_get_context(request),
                    })
                payload['client'] = client_id
            else:
                payload['client'] = request.session.get('client_id')

            try:
                resp = _api_post(request, '/api/dynamic-models/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 201:
                    _flash(request, 'Dynamic model created successfully!', 'success')
                    return redirect('dynamic_model_list')
                errors = _error_list_from_response(resp, 'Failed to create dynamic model.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'dynamic_models/create.html', {
        'form': form,
        'errors': errors,
        'messages': messages,
        'role': role,
        **_get_context(request),
    })


def dynamic_model_edit(request, pk):
    permission_redirect = _require_module_permission(request, 'dynamic_models.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    errors = []
    messages = _pop_messages(request)
    role = request.session.get('role', 'employee')
    is_superadmin = role == 'superadmin'

    try:
        get_resp = _api_get(request, f'/api/dynamic-models/{pk}/')
        redir = _handle_unauthorized(get_resp, request)
        if redir:
            return redir
        if get_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        model_data = get_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_models/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            'role': role,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = DynamicModelForm(request.POST)
        if form.is_valid():
            payload = {
                'name': form.cleaned_data['name'],
                'slug': form.cleaned_data['slug'],
                'show_in_employee_form': bool(form.cleaned_data.get('show_in_employee_form')),
            }
            if is_superadmin:
                payload['client'] = request.POST.get('client') or model_data.get('client')
            else:
                payload['client'] = request.session.get('client_id') or model_data.get('client')
            try:
                resp = _api_put(request, f'/api/dynamic-models/{pk}/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 200:
                    _flash(request, 'Dynamic model updated successfully!', 'success')
                    return redirect('dynamic_model_list')
                errors = _error_list_from_response(resp, 'Failed to update dynamic model.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
    else:
        form = DynamicModelForm(initial=model_data)

    return render(request, 'dynamic_models/edit.html', {
        'form': form,
        'dynamic_model': model_data,
        'errors': errors,
        'messages': messages,
        'role': role,
        **_get_context(request),
    })


@require_POST
def dynamic_model_delete(request, pk):
    permission_redirect = _require_module_permission(request, 'dynamic_models.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    try:
        resp = _api_delete(request, f'/api/dynamic-models/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Dynamic model deleted.', 'success')
        else:
            _flash(request, 'Failed to delete dynamic model.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('dynamic_model_list')


@require_POST
def dynamic_model_create_attendance(request):
    permission_redirect = _require_module_permission(request, 'attendance.create')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'attendance')
    if addon_redirect:
        return addon_redirect
    role = request.session.get('role', 'employee')
    payload = {}
    if role == 'superadmin':
        client_id = request.POST.get('client')
        if not client_id:
            _flash(request, 'For superadmin, provide client id to create Attendance module.', 'error')
            return redirect('dynamic_model_list')
        payload['client'] = client_id

    try:
        resp = _api_post(request, '/api/dynamic-models/create-attendance/', payload)
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code in (200, 201):
            msg = resp.json().get('detail', 'Attendance module created.')
            _flash(request, msg, 'success')
        else:
            errors = _error_list_from_response(resp, 'Failed to create attendance module.')
            _flash(request, '; '.join(errors), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')

    return redirect('dynamic_model_list')


def dynamic_field_list(request, model_id):
    permission_redirect = _require_module_permission(request, 'dynamic_models.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    messages = _pop_messages(request)
    try:
        model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        redir = _handle_unauthorized(model_resp, request)
        if redir:
            return redir
        if model_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        dynamic_model = model_resp.json()

        resp = _api_get(request, f'/api/dynamic-fields/?dynamic_model={model_id}')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        data = resp.json() if resp.status_code == 200 else []
        dynamic_fields = data.get('results', data) if isinstance(data, dict) else data
        dynamic_fields = _filter_visible_dynamic_fields(request, dynamic_fields)
    except requests.exceptions.ConnectionError:
        dynamic_model = {}
        dynamic_fields = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'dynamic_fields/list.html', {
        'dynamic_model': dynamic_model,
        'dynamic_fields': dynamic_fields,
        'messages': messages,
        **_get_context(request),
    })


def dynamic_field_create(request, model_id):
    permission_redirect = _require_module_permission(request, 'dynamic_models.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    form = DynamicFieldForm()
    errors = []
    messages = _pop_messages(request)

    try:
        model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        redir = _handle_unauthorized(model_resp, request)
        if redir:
            return redir
        if model_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        dynamic_model = model_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_fields/create.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = DynamicFieldForm(request.POST)
        if form.is_valid():
            use_dropdown = bool(form.cleaned_data.get('use_dropdown'))
            choices_raw = form.cleaned_data.get('choices_json', '').strip()
            choices_json = []
            if use_dropdown and choices_raw:
                try:
                    try:
                        parsed = json.loads(choices_raw)
                        if not isinstance(parsed, list):
                            raise ValueError('choices_json must be a list.')
                        choices_json = [str(x).strip() for x in parsed if str(x).strip()]
                    except json.JSONDecodeError:
                        # Also accept simple comma-separated values for convenience.
                        choices_json = [x.strip() for x in choices_raw.split(',') if x.strip()]
                    if not choices_json:
                        raise ValueError('Empty choices.')
                except (ValueError, json.JSONDecodeError):
                    errors = ['Choices must be JSON array (e.g. ["A","B"]) or comma-separated (e.g. A,B).']
                    return render(request, 'dynamic_fields/create.html', {
                        'form': form,
                        'dynamic_model': dynamic_model,
                        'errors': errors,
                        'messages': messages,
                        **_get_context(request),
                    })
            elif use_dropdown and not choices_raw:
                errors = ['Choices are required when Use Dropdown is Yes.']
                return render(request, 'dynamic_fields/create.html', {
                    'form': form,
                    'dynamic_model': dynamic_model,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            payload = {
                'dynamic_model': model_id,
                'name': form.cleaned_data['name'],
                'key': form.cleaned_data['key'],
                'field_type': form.cleaned_data['field_type'],
                'required': bool(form.cleaned_data.get('required')),
                'visible_to_users': bool(form.cleaned_data.get('visible_to_users')),
                'choices_json': choices_json,
                'sort_order': form.cleaned_data.get('sort_order') or 0,
            }

            try:
                resp = _api_post(request, '/api/dynamic-fields/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 201:
                    _flash(request, 'Dynamic field created successfully!', 'success')
                    return redirect('dynamic_field_list', model_id=model_id)
                errors = _error_list_from_response(resp, 'Failed to create dynamic field.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'dynamic_fields/create.html', {
        'form': form,
        'dynamic_model': dynamic_model,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


def dynamic_field_edit(request, model_id, pk):
    permission_redirect = _require_module_permission(request, 'dynamic_models.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    errors = []
    messages = _pop_messages(request)

    try:
        model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        redir = _handle_unauthorized(model_resp, request)
        if redir:
            return redir
        if model_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        dynamic_model = model_resp.json()

        get_resp = _api_get(request, f'/api/dynamic-fields/{pk}/')
        redir = _handle_unauthorized(get_resp, request)
        if redir:
            return redir
        if get_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        field_data = get_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_fields/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = DynamicFieldForm(request.POST)
        if form.is_valid():
            use_dropdown = bool(form.cleaned_data.get('use_dropdown'))
            choices_raw = form.cleaned_data.get('choices_json', '').strip()
            choices_json = []
            if use_dropdown and choices_raw:
                try:
                    try:
                        parsed = json.loads(choices_raw)
                        if not isinstance(parsed, list):
                            raise ValueError('choices_json must be a list.')
                        choices_json = [str(x).strip() for x in parsed if str(x).strip()]
                    except json.JSONDecodeError:
                        # Also accept simple comma-separated values for convenience.
                        choices_json = [x.strip() for x in choices_raw.split(',') if x.strip()]
                    if not choices_json:
                        raise ValueError('Empty choices.')
                except (ValueError, json.JSONDecodeError):
                    errors = ['Choices must be JSON array (e.g. ["A","B"]) or comma-separated (e.g. A,B).']
                    return render(request, 'dynamic_fields/edit.html', {
                        'form': form,
                        'dynamic_model': dynamic_model,
                        'dynamic_field': field_data,
                        'errors': errors,
                        'messages': messages,
                        **_get_context(request),
                    })
            elif use_dropdown and not choices_raw:
                errors = ['Choices are required when Use Dropdown is Yes.']
                return render(request, 'dynamic_fields/edit.html', {
                    'form': form,
                    'dynamic_model': dynamic_model,
                    'dynamic_field': field_data,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            payload = {
                'dynamic_model': model_id,
                'name': form.cleaned_data['name'],
                'key': form.cleaned_data['key'],
                'field_type': form.cleaned_data['field_type'],
                'required': bool(form.cleaned_data.get('required')),
                'visible_to_users': bool(form.cleaned_data.get('visible_to_users')),
                'choices_json': choices_json,
                'sort_order': form.cleaned_data.get('sort_order') or 0,
            }
            try:
                resp = _api_put(request, f'/api/dynamic-fields/{pk}/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 200:
                    _flash(request, 'Dynamic field updated successfully!', 'success')
                    return redirect('dynamic_field_list', model_id=model_id)
                errors = _error_list_from_response(resp, 'Failed to update dynamic field.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
    else:
        initial = field_data.copy()
        initial['choices_json'] = json.dumps(initial.get('choices_json', []))
        initial['use_dropdown'] = bool(initial.get('choices_json'))
        initial['visible_to_users'] = field_data.get('visible_to_users', True)
        form = DynamicFieldForm(initial=initial)

    return render(request, 'dynamic_fields/edit.html', {
        'form': form,
        'dynamic_model': dynamic_model,
        'dynamic_field': field_data,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


@require_POST
def dynamic_field_delete(request, model_id, pk):
    permission_redirect = _require_module_permission(request, 'dynamic_models.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    try:
        resp = _api_delete(request, f'/api/dynamic-fields/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Dynamic field deleted.', 'success')
        else:
            _flash(request, 'Failed to delete dynamic field.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('dynamic_field_list', model_id=model_id)


def dynamic_record_list(request, model_id):
    permission_redirect = _require_module_permission(request, f'dynamic_model.{model_id}.view')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    messages = _pop_messages(request)
    try:
        model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        redir = _handle_unauthorized(model_resp, request)
        if redir:
            return redir
        if model_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        dynamic_model = model_resp.json()

        resp = _api_get(request, f'/api/dynamic-records/?dynamic_model={model_id}')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        data = resp.json() if resp.status_code == 200 else []
        dynamic_records = data.get('results', data) if isinstance(data, dict) else data
    except requests.exceptions.ConnectionError:
        dynamic_model = {}
        dynamic_records = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'dynamic_records/list.html', {
        'dynamic_model': dynamic_model,
        'dynamic_records': dynamic_records,
        'messages': messages,
        **_get_context(request),
    })


def dynamic_record_create(request, model_id):
    permission_redirect = _require_module_permission(request, f'dynamic_model.{model_id}.create')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    form = DynamicRecordForm()
    errors = []
    messages = _pop_messages(request)

    try:
        model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        redir = _handle_unauthorized(model_resp, request)
        if redir:
            return redir
        if model_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        dynamic_model = model_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_records/create.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = DynamicRecordForm(request.POST)
        if form.is_valid():
            try:
                data_json = json.loads(form.cleaned_data['data_json'])
                if not isinstance(data_json, dict):
                    raise ValueError('data_json must be an object.')
            except (ValueError, json.JSONDecodeError):
                errors = ['Data JSON must be a valid JSON object, e.g. {"key":"value"}']
                return render(request, 'dynamic_records/create.html', {
                    'form': form,
                    'dynamic_model': dynamic_model,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            payload = {
                'dynamic_model': model_id,
                'data': data_json,
            }
            try:
                resp = _api_post(request, '/api/dynamic-records/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 201:
                    _flash(request, 'Dynamic record created successfully!', 'success')
                    return redirect('dynamic_record_list', model_id=model_id)
                errors = _error_list_from_response(resp, 'Failed to create record.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']

    return render(request, 'dynamic_records/create.html', {
        'form': form,
        'dynamic_model': dynamic_model,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


def dynamic_record_edit(request, model_id, pk):
    permission_redirect = _require_module_permission(request, f'dynamic_model.{model_id}.edit')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    errors = []
    messages = _pop_messages(request)

    try:
        model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        redir = _handle_unauthorized(model_resp, request)
        if redir:
            return redir
        if model_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        dynamic_model = model_resp.json()

        get_resp = _api_get(request, f'/api/dynamic-records/{pk}/')
        redir = _handle_unauthorized(get_resp, request)
        if redir:
            return redir
        if get_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        record_data = get_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_records/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })

    if request.method == 'POST':
        form = DynamicRecordForm(request.POST)
        if form.is_valid():
            try:
                data_json = json.loads(form.cleaned_data['data_json'])
                if not isinstance(data_json, dict):
                    raise ValueError('data_json must be an object.')
            except (ValueError, json.JSONDecodeError):
                errors = ['Data JSON must be a valid JSON object, e.g. {"key":"value"}']
                return render(request, 'dynamic_records/edit.html', {
                    'form': form,
                    'dynamic_model': dynamic_model,
                    'dynamic_record': record_data,
                    'errors': errors,
                    'messages': messages,
                    **_get_context(request),
                })

            payload = {
                'dynamic_model': model_id,
                'data': data_json,
            }
            try:
                resp = _api_put(request, f'/api/dynamic-records/{pk}/', payload)
                redir = _handle_unauthorized(resp, request)
                if redir:
                    return redir
                if resp.status_code == 200:
                    _flash(request, 'Dynamic record updated successfully!', 'success')
                    return redirect('dynamic_record_list', model_id=model_id)
                errors = _error_list_from_response(resp, 'Failed to update record.')
            except requests.exceptions.ConnectionError:
                errors = ['Backend server unreachable.']
    else:
        form = DynamicRecordForm(initial={'data_json': json.dumps(record_data.get('data', {}), indent=2)})

    return render(request, 'dynamic_records/edit.html', {
        'form': form,
        'dynamic_model': dynamic_model,
        'dynamic_record': record_data,
        'errors': errors,
        'messages': messages,
        **_get_context(request),
    })


@require_POST
def dynamic_record_delete(request, model_id, pk):
    permission_redirect = _require_module_permission(request, f'dynamic_model.{model_id}.delete')
    if permission_redirect:
        return permission_redirect
    addon_redirect = _require_addon(request, 'dynamic_models')
    if addon_redirect:
        return addon_redirect
    try:
        resp = _api_delete(request, f'/api/dynamic-records/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Dynamic record deleted.', 'success')
        else:
            _flash(request, 'Failed to delete dynamic record.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('dynamic_record_list', model_id=model_id)


# Dynamic Entity (form-based record screens per dynamic model)
def _load_dynamic_model_and_fields(request, model_id):
    model_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
    redir = _handle_unauthorized(model_resp, request)
    if redir:
        return redir, None, None
    if model_resp.status_code == 404:
        return render(request, 'errors/404.html', status=404), None, None
    dynamic_model = model_resp.json()

    fields_resp = _api_get(request, f'/api/dynamic-fields/?dynamic_model={model_id}')
    redir = _handle_unauthorized(fields_resp, request)
    if redir:
        return redir, None, None
    fields_data = fields_resp.json() if fields_resp.status_code == 200 else []
    fields = fields_data.get('results', fields_data) if isinstance(fields_data, dict) else fields_data
    return None, dynamic_model, fields


def dynamic_entity_list(request, model_id):
    probe_model = None
    try:
        probe_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        if probe_resp.status_code == 200:
            probe_model = probe_resp.json()
            is_attendance_model = str(probe_model.get('slug', '')).lower() == 'attendance'
            if is_attendance_model:
                if not _has_any_module_permission(
                    request,
                    ['attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete'],
                ):
                    _flash(request, 'You do not have permission to access this module.', 'error')
                    return redirect('dashboard')
            else:
                permission_redirect = _require_module_permission(request, f'dynamic_model.{model_id}.view')
                if permission_redirect:
                    return permission_redirect
    except requests.exceptions.ConnectionError:
        pass
    addon_redirect = _require_addon(
        request,
        'attendance' if probe_model and str(probe_model.get('slug', '')).lower() == 'attendance' else 'dynamic_models'
    )
    if addon_redirect:
        return addon_redirect
    messages = _pop_messages(request)
    attendance_summary = None
    attendance_employees = []
    selected_employee_id = (request.GET.get('employee') or '').strip()
    can_view_all_attendance = False
    can_manage_attendance_template = False
    attendance_add_locked = False
    attendance_open_record_id = None
    current_employee_id = request.session.get('employee_id')
    current_employee_role = (request.session.get('employee_role') or '').strip().lower()
    try:
        redir, dynamic_model, fields = _load_dynamic_model_and_fields(request, model_id)
        if redir:
            return redir
        fields = _filter_visible_dynamic_fields(request, fields)
        is_attendance = str(dynamic_model.get('slug', '')).lower() == 'attendance'
        if is_attendance:
            addon_redirect = _require_addon(request, 'attendance')
            if addon_redirect:
                return addon_redirect
            can_manage_attendance_template = (
                request.session.get('role') in ('superadmin', 'admin')
                or _has_any_module_permission(request, ['attendance.create', 'attendance.edit'])
            )

        records_params = {'dynamic_model': model_id}
        if is_attendance:
            can_view_all_attendance = (
                request.session.get('role') in ('superadmin', 'admin')
                or current_employee_role in ('hr', 'manager')
            )
            employees_resp = _api_get(request, '/api/employees/')
            employees_rows = []
            if employees_resp.status_code == 200:
                employees_data = employees_resp.json()
                employees_rows = (
                    employees_data.get('results', employees_data)
                    if isinstance(employees_data, dict) else employees_data
                )
            attendance_employees = employees_rows

            if can_view_all_attendance and selected_employee_id:
                records_params['employee'] = selected_employee_id
            elif not can_view_all_attendance and current_employee_id:
                records_params['employee'] = current_employee_id

        records_resp = _api_get(request, '/api/dynamic-records/', params=records_params)
        redir = _handle_unauthorized(records_resp, request)
        if redir:
            return redir
        records_data = records_resp.json() if records_resp.status_code == 200 else []
        records = records_data.get('results', records_data) if isinstance(records_data, dict) else records_data

        if is_attendance:
            employee_name_map = {
                str(emp.get('id')): f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
                for emp in attendance_employees
            }

            if can_view_all_attendance and not selected_employee_id:
                today_iso = timezone.localdate().isoformat()
                today_records = []
                for rec in records:
                    if str((rec.get('data') or {}).get('attendance_date')) == today_iso:
                        today_records.append(rec)
                records = today_records

                present_ids = {
                    str(rec.get('employee'))
                    for rec in records
                    if str((rec.get('data') or {}).get('status') or 'present').lower() == 'present'
                }
                total_employees = len(attendance_employees)
                attendance_summary = {
                    'date': today_iso,
                    'present': len(present_ids),
                    'absent': max(total_employees - len(present_ids), 0),
                }

            for rec in records:
                rec_data = rec.get('data', {})
                rec['total_time'] = _attendance_total_time(rec_data) or '-'
                rec['employee_name'] = employee_name_map.get(str(rec.get('employee')), f"Employee #{rec.get('employee')}")
                rec['is_open_attendance'] = bool(rec_data.get('check_in') and not rec_data.get('check_out'))

            # For regular employee login, lock Add Attendance after first check-in of the day.
            if (not can_view_all_attendance) and current_employee_id:
                today_iso = timezone.localdate().isoformat()
                today_rows = [
                    row for row in records
                    if str(row.get('employee')) == str(current_employee_id)
                    and str((row.get('data') or {}).get('attendance_date')) == today_iso
                ]
                if today_rows:
                    attendance_add_locked = True
                    open_row = next((row for row in today_rows if row.get('is_open_attendance')), None)
                    if open_row:
                        attendance_open_record_id = open_row.get('id')
    except requests.exceptions.ConnectionError:
        dynamic_model = {}
        fields = []
        records = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'dynamic_entities/list.html', {
        'dynamic_model': dynamic_model,
        'fields': fields,
        'records': records,
        'attendance_summary': attendance_summary,
        'attendance_employees': attendance_employees,
        'selected_employee_id': selected_employee_id,
        'can_view_all_attendance': can_view_all_attendance,
        'can_manage_attendance_template': can_manage_attendance_template,
        'attendance_add_locked': attendance_add_locked,
        'attendance_open_record_id': attendance_open_record_id,
        'messages': messages,
        **_attendance_feature_flags(request),
        **_get_context(request),
    })


@require_POST
def dynamic_entity_punch(request, model_id):
    permission_redirect = _require_module_permission(request, 'attendance.edit')
    if permission_redirect:
        return permission_redirect
    """
    Attendance punch flow:
    - first punch of day => Punch In (create)
    - second punch of day => Punch Out (update existing open record)
    """
    try:
        redir, dynamic_model, fields = _load_dynamic_model_and_fields(request, model_id)
        if redir:
            return redir
        fields = _filter_visible_dynamic_fields(request, fields)

        if str(dynamic_model.get('slug', '')).lower() != 'attendance':
            _flash(request, 'Punch is only available for Attendance model.', 'error')
            return redirect('dynamic_entity_list', model_id=model_id)
        addon_redirect = _require_addon(request, 'attendance')
        if addon_redirect:
            return addon_redirect

        session_employee_id = request.session.get('employee_id')
        session_employee_role = (request.session.get('employee_role') or '').strip().lower()
        is_regular_employee = (
            request.session.get('role') == 'employee'
            and session_employee_role == 'employee'
        )
        employee_id = str(session_employee_id) if is_regular_employee and session_employee_id else request.POST.get('employee_id')
        if not employee_id:
            _flash(request, 'Employee ID is required.', 'error')
            return redirect('dynamic_entity_list', model_id=model_id)

        today = timezone.localdate().isoformat()
        now_time = timezone.localtime().strftime('%H:%M:%S')
        shift = (request.POST.get('shift') or '').strip()
        remarks = (request.POST.get('remarks') or '').strip()
        location_lat = (request.POST.get('location_lat') or '').strip()
        location_lng = (request.POST.get('location_lng') or '').strip()
        selfie_url = (request.POST.get('selfie_url') or '').strip()
        flags = _attendance_feature_flags(request)

        if flags.get('attendance_location_required') and (not location_lat or not location_lng):
            _flash(request, 'Location is required for this client attendance plan.', 'error')
            return redirect('dynamic_entity_list', model_id=model_id)
        if flags.get('attendance_selfie_required') and not selfie_url:
            _flash(request, 'Selfie is required for this client attendance plan.', 'error')
            return redirect('dynamic_entity_list', model_id=model_id)

        # Find open attendance for employee (today + check_in exists + check_out missing).
        rec_resp = _api_get(
            request,
            f'/api/dynamic-records/?dynamic_model={model_id}&employee={employee_id}',
        )
        redir = _handle_unauthorized(rec_resp, request)
        if redir:
            return redir

        records = []
        if rec_resp.status_code == 200:
            rec_data = rec_resp.json()
            records = rec_data.get('results', rec_data) if isinstance(rec_data, dict) else rec_data

        today_record = None
        open_record = None
        for rec in records:
            data = rec.get('data', {})
            if str(data.get('attendance_date')) != today:
                continue
            today_record = rec
            if data.get('check_in') and not data.get('check_out'):
                open_record = rec
            break

        if open_record:
            # Punch Out
            data = dict(open_record.get('data', {}))
            data['check_out'] = now_time
            if remarks:
                data['remarks'] = remarks
            if flags.get('attendance_location_required'):
                data['location_lat'] = location_lat
                data['location_lng'] = location_lng
            if flags.get('attendance_selfie_required'):
                data['selfie_url'] = selfie_url
            payload = {
                'dynamic_model': model_id,
                'employee': employee_id,
                'data': data,
            }
            upd_resp = _api_put(request, f"/api/dynamic-records/{open_record['id']}/", payload)
            redir = _handle_unauthorized(upd_resp, request)
            if redir:
                return redir
            if upd_resp.status_code == 200:
                _flash(request, f'Punch Out saved at {now_time}.', 'success')
            else:
                _flash(request, '; '.join(_error_list_from_response(upd_resp, 'Failed to save Punch Out.')), 'error')
            return redirect('dynamic_entity_list', model_id=model_id)

        if today_record:
            _flash(request, 'Attendance already completed for today. You can only check in/check out once per day.', 'error')
            return redirect('dynamic_entity_list', model_id=model_id)

        # Punch In
        data = {
            'attendance_date': today,
            'status': 'present',
            'check_in': now_time,
        }
        if shift:
            data['shift'] = shift
        if remarks:
            data['remarks'] = remarks
        if flags.get('attendance_location_required'):
            data['location_lat'] = location_lat
            data['location_lng'] = location_lng
        if flags.get('attendance_selfie_required'):
            data['selfie_url'] = selfie_url

        payload = {
            'dynamic_model': model_id,
            'employee': employee_id,
            'data': data,
        }
        create_resp = _api_post(request, '/api/dynamic-records/', payload)
        redir = _handle_unauthorized(create_resp, request)
        if redir:
            return redir
        if create_resp.status_code == 201:
            _flash(request, f'Punch In saved at {now_time}.', 'success')
        else:
            _flash(request, '; '.join(_error_list_from_response(create_resp, 'Failed to save Punch In.')), 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')

    return redirect('dynamic_entity_list', model_id=model_id)


def dynamic_entity_create(request, model_id):
    probe_model = None
    try:
        probe_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        if probe_resp.status_code == 200:
            probe_model = probe_resp.json()
            is_attendance_model = str(probe_model.get('slug', '')).lower() == 'attendance'
            if is_attendance_model:
                permission_redirect = None
                if not _has_any_module_permission(request, ['attendance.create', 'attendance.edit']):
                    _flash(request, 'You do not have permission to mark attendance.', 'error')
                    permission_redirect = redirect('dashboard')
            else:
                permission_redirect = _require_module_permission(request, f'dynamic_model.{model_id}.create')
            if permission_redirect:
                return permission_redirect
    except requests.exceptions.ConnectionError:
        pass
    addon_redirect = _require_addon(
        request,
        'attendance' if probe_model and str(probe_model.get('slug', '')).lower() == 'attendance' else 'dynamic_models'
    )
    if addon_redirect:
        return addon_redirect
    errors = []
    messages = _pop_messages(request)

    try:
        redir, dynamic_model, fields = _load_dynamic_model_and_fields(request, model_id)
        if redir:
            return redir
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_entities/create.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })
    is_attendance = str(dynamic_model.get('slug', '')).lower() == 'attendance'
    if is_attendance:
        addon_redirect = _require_addon(request, 'attendance')
        if addon_redirect:
            return addon_redirect
    attendance_flags = _attendance_feature_flags(request)
    current_time = timezone.localtime().strftime('%H:%M:%S')
    attendance_locked_employee_id = None
    if is_attendance:
        session_employee_role = (request.session.get('employee_role') or '').strip().lower()
        if request.session.get('role') == 'employee' and session_employee_role == 'employee':
            attendance_locked_employee_id = request.session.get('employee_id')

    if request.method == 'POST':
        data = {}
        payload = {'dynamic_model': model_id}
        if is_attendance:
            session_employee_id = request.session.get('employee_id')
            session_employee_role = (request.session.get('employee_role') or '').strip().lower()
            is_regular_employee = (
                request.session.get('role') == 'employee'
                and session_employee_role == 'employee'
            )
            employee_id = (
                str(session_employee_id)
                if is_regular_employee and session_employee_id
                else (request.POST.get('employee_id') or '').strip()
            )
            if not employee_id:
                errors = ['Employee ID is required for attendance check-in.']
                return render(request, 'dynamic_entities/create.html', {
                    'dynamic_model': dynamic_model,
                    'fields': fields,
                    'is_attendance': is_attendance,
                    'current_time': current_time,
                    'attendance_locked_employee_id': attendance_locked_employee_id,
                    'errors': errors,
                    'messages': messages,
                    **attendance_flags,
                    **_get_context(request),
                })

            today = timezone.localdate().isoformat()
            rec_resp = _api_get(
                request,
                f'/api/dynamic-records/?dynamic_model={model_id}&employee={employee_id}',
            )
            redir = _handle_unauthorized(rec_resp, request)
            if redir:
                return redir
            if rec_resp.status_code == 200:
                rec_data = rec_resp.json()
                records = rec_data.get('results', rec_data) if isinstance(rec_data, dict) else rec_data
                already_exists = any(
                    str((r.get('data') or {}).get('attendance_date')) == today
                    for r in records
                )
                if already_exists:
                    errors = ['This employee already has attendance for today. Only one check-in/check-out is allowed per day.']
                    return render(request, 'dynamic_entities/create.html', {
                        'dynamic_model': dynamic_model,
                        'fields': fields,
                        'is_attendance': is_attendance,
                        'current_time': current_time,
                        'attendance_locked_employee_id': attendance_locked_employee_id,
                        'errors': errors,
                        'messages': messages,
                        **attendance_flags,
                        **_get_context(request),
                    })

            payload['employee'] = employee_id
            data['attendance_date'] = today
            data['status'] = (request.POST.get('status') or 'present').strip()
            shift = (request.POST.get('shift') or '').strip()
            remarks = (request.POST.get('remarks') or '').strip()
            if shift:
                data['shift'] = shift
            if remarks:
                data['remarks'] = remarks
            data['check_in'] = current_time
        else:
            for field in fields:
                key = field.get('key')
                field_type = field.get('field_type')
                form_key = f'df_{key}'

                if field_type == 'boolean':
                    raw = request.POST.get(form_key)
                    value = 'true' if raw in ('true', 'on', '1') else 'false'
                elif field_type in ('file', 'image'):
                    uploaded = request.FILES.get(form_key)
                    value = _store_uploaded_dynamic_file(uploaded, folder=f'dynamic_uploads/model_{model_id}') if uploaded else ''
                else:
                    value = request.POST.get(form_key, '').strip()

                if value != '':
                    data[key] = value

        payload['data'] = data
        try:
            resp = _api_post(request, '/api/dynamic-records/', payload)
            redir = _handle_unauthorized(resp, request)
            if redir:
                return redir
            if resp.status_code == 201:
                msg = 'Check-in saved successfully!' if is_attendance else f"{dynamic_model.get('name', 'Record')} created successfully!"
                _flash(request, msg, 'success')
                return redirect('dynamic_entity_list', model_id=model_id)
            errors = _error_list_from_response(resp, 'Failed to create record.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'dynamic_entities/create.html', {
        'dynamic_model': dynamic_model,
        'fields': fields,
        'is_attendance': is_attendance,
        'current_time': current_time,
        'attendance_locked_employee_id': attendance_locked_employee_id,
        'errors': errors,
        'messages': messages,
        **attendance_flags,
        **_get_context(request),
    })


def dynamic_entity_edit(request, model_id, pk):
    probe_model = None
    try:
        probe_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        if probe_resp.status_code == 200:
            probe_model = probe_resp.json()
            is_attendance_model = str(probe_model.get('slug', '')).lower() == 'attendance'
            permission_redirect = _require_module_permission(
                request,
                'attendance.edit' if is_attendance_model else f'dynamic_model.{model_id}.edit'
            )
            if permission_redirect:
                return permission_redirect
    except requests.exceptions.ConnectionError:
        pass
    addon_redirect = _require_addon(
        request,
        'attendance' if probe_model and str(probe_model.get('slug', '')).lower() == 'attendance' else 'dynamic_models'
    )
    if addon_redirect:
        return addon_redirect
    errors = []
    messages = _pop_messages(request)

    try:
        redir, dynamic_model, fields = _load_dynamic_model_and_fields(request, model_id)
        if redir:
            return redir

        rec_resp = _api_get(request, f'/api/dynamic-records/{pk}/')
        redir = _handle_unauthorized(rec_resp, request)
        if redir:
            return redir
        if rec_resp.status_code == 404:
            return render(request, 'errors/404.html', status=404)
        record = rec_resp.json()
    except requests.exceptions.ConnectionError:
        return render(request, 'dynamic_entities/edit.html', {
            'errors': ['Backend server unreachable.'],
            'messages': messages,
            **_get_context(request),
        })
    is_attendance = str(dynamic_model.get('slug', '')).lower() == 'attendance'
    if is_attendance:
        addon_redirect = _require_addon(request, 'attendance')
        if addon_redirect:
            return addon_redirect
    attendance_flags = _attendance_feature_flags(request)
    current_time = timezone.localtime().strftime('%H:%M:%S')
    attendance_total_time = ''
    attendance_total_time_preview = ''

    if is_attendance:
        existing_data = record.get('data', {})
        attendance_total_time = _attendance_total_time(existing_data)
        if not attendance_total_time and existing_data.get('check_in'):
            attendance_total_time_preview = _attendance_total_time(existing_data, end_override=current_time)

    if request.method == 'POST':
        if is_attendance:
            existing = dict(record.get('data', {}))
            if existing.get('check_out'):
                errors = ['Check-out already saved for this attendance record.']
                return render(request, 'dynamic_entities/edit.html', {
                    'dynamic_model': dynamic_model,
                    'fields': fields,
                    'record': record,
                    'is_attendance': is_attendance,
                    'current_time': current_time,
                    'attendance_total_time': attendance_total_time,
                    'attendance_total_time_preview': attendance_total_time_preview,
                    'errors': errors,
                    'messages': messages,
                    **attendance_flags,
                    **_get_context(request),
                })
            remarks = (request.POST.get('remarks') or '').strip()
            if remarks:
                existing['remarks'] = remarks
            existing['check_out'] = current_time
            payload = {
                'dynamic_model': model_id,
                'employee': record.get('employee'),
                'data': existing,
            }
        else:
            data = {}
            for field in fields:
                key = field.get('key')
                field_type = field.get('field_type')
                form_key = f'df_{key}'

                if field_type == 'boolean':
                    raw = request.POST.get(form_key)
                    value = 'true' if raw in ('true', 'on', '1') else 'false'
                elif field_type in ('file', 'image'):
                    uploaded = request.FILES.get(form_key)
                    value = _store_uploaded_dynamic_file(uploaded, folder=f'dynamic_uploads/model_{model_id}') if uploaded else ''
                else:
                    value = request.POST.get(form_key, '').strip()

                if value != '':
                    data[key] = value

            payload = {'dynamic_model': model_id, 'data': data}

        try:
            resp = _api_put(request, f'/api/dynamic-records/{pk}/', payload)
            redir = _handle_unauthorized(resp, request)
            if redir:
                return redir
            if resp.status_code == 200:
                msg = 'Check-out saved successfully!' if is_attendance else f"{dynamic_model.get('name', 'Record')} updated successfully!"
                _flash(request, msg, 'success')
                return redirect('dynamic_entity_list', model_id=model_id)
            errors = _error_list_from_response(resp, 'Failed to update record.')
        except requests.exceptions.ConnectionError:
            errors = ['Backend server unreachable.']

    return render(request, 'dynamic_entities/edit.html', {
        'dynamic_model': dynamic_model,
        'fields': fields,
        'record': record,
        'is_attendance': is_attendance,
        'current_time': current_time,
        'attendance_total_time': attendance_total_time,
        'attendance_total_time_preview': attendance_total_time_preview,
        'errors': errors,
        'messages': messages,
        **attendance_flags,
        **_get_context(request),
    })


@require_POST
def dynamic_entity_delete(request, model_id, pk):
    probe_model = None
    try:
        probe_resp = _api_get(request, f'/api/dynamic-models/{model_id}/')
        if probe_resp.status_code == 200:
            probe_model = probe_resp.json()
            is_attendance_model = str(probe_model.get('slug', '')).lower() == 'attendance'
            permission_redirect = _require_module_permission(
                request,
                'attendance.delete' if is_attendance_model else f'dynamic_model.{model_id}.delete'
            )
            if permission_redirect:
                return permission_redirect
    except requests.exceptions.ConnectionError:
        pass
    addon_redirect = _require_addon(
        request,
        'attendance' if probe_model and str(probe_model.get('slug', '')).lower() == 'attendance' else 'dynamic_models'
    )
    if addon_redirect:
        return addon_redirect
    try:
        resp = _api_delete(request, f'/api/dynamic-records/{pk}/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        if resp.status_code == 204:
            _flash(request, 'Record deleted.', 'success')
        else:
            _flash(request, 'Failed to delete record.', 'error')
    except requests.exceptions.ConnectionError:
        _flash(request, 'Backend server unreachable.', 'error')
    return redirect('dynamic_entity_list', model_id=model_id)
