import requests
import json
import datetime
import calendar
import re
import os
import uuid
from django.conf import settings
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from django.utils.text import slugify

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

ADDON_KEYS = {
    'custom_fields',
    'dynamic_models',
    'attendance',
    'attendance_location',
    'attendance_selfie_location',
    'leave_management',
    'holidays',
    'settings',
    'policy',
}
ADDON_OPTIONS = [
    ('custom_fields', 'Custom Fields'),
    ('dynamic_models', 'Dynamic Models'),
    ('attendance', 'Attendance'),
    ('attendance_location', 'Attendance + Location'),
    ('attendance_selfie_location', 'Attendance + Selfie + Location'),
    ('leave_management', 'Leave Management'),
    ('holidays', 'Holidays'),
    ('settings', 'Settings'),
    ('policy', 'Policy'),
]

STATIC_PERMISSION_KEYS = {
    'employees.view', 'employees.create', 'employees.edit', 'employees.delete',
    'attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete',
    'leaves.view', 'leaves.create', 'leaves.edit', 'leaves.delete', 'leaves.approve',
    'holidays.view', 'holidays.create', 'holidays.edit', 'holidays.delete',
    'custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete',
    'dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete',
}

LEGACY_PERMISSION_MAP = {
    'employees': ['employees.view', 'employees.create', 'employees.edit', 'employees.delete'],
    'attendance': ['attendance.view', 'attendance.create', 'attendance.edit', 'attendance.delete'],
    'leaves': ['leaves.view', 'leaves.create', 'leaves.edit', 'leaves.delete', 'leaves.approve'],
    'holidays': ['holidays.view', 'holidays.create', 'holidays.edit', 'holidays.delete'],
    'custom_fields': ['custom_fields.view', 'custom_fields.create', 'custom_fields.edit', 'custom_fields.delete'],
    'dynamic_models': ['dynamic_models.view', 'dynamic_models.create', 'dynamic_models.edit', 'dynamic_models.delete'],
}
ADDON_VIEW_PERMISSION_MAP = {
    'custom_fields': 'custom_fields.view',
    'dynamic_models': 'dynamic_models.view',
    'attendance': 'attendance.view',
    'leave_management': 'leaves.view',
    'holidays': 'holidays.view',
    'policy': 'policy.view',
}


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _auth_headers(request):
    """Return Authorization header using the token stored in the session."""
    token = request.session.get('access_token', '')
    return {'Authorization': f'Bearer {token}'}


def _api_get(request, path, params=None):
    """GET from backend API.  Returns (data, response)."""
    resp = requests.get(
        f'{API}{path}',
        headers=_auth_headers(request),
        params=params,
        timeout=10,
    )
    return resp


def _api_post(request, path, data):
    resp = requests.post(
        f'{API}{path}',
        json=data,
        headers=_auth_headers(request),
        timeout=10,
    )
    return resp


def _api_put(request, path, data):
    resp = requests.put(
        f'{API}{path}',
        json=data,
        headers=_auth_headers(request),
        timeout=10,
    )
    return resp


def _api_delete(request, path):
    resp = requests.delete(
        f'{API}{path}',
        headers=_auth_headers(request),
        timeout=10,
    )
    return resp


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
        return datetime.datetime.combine(datetime.date.today(), value)

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            parsed_time = datetime.datetime.strptime(raw, fmt).time()
            return datetime.datetime.combine(datetime.date.today(), parsed_time)
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
    today = datetime.date.today()
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
        if key in STATIC_PERMISSION_KEYS or key == 'policy.view' or re.fullmatch(r'dynamic_model\.\d+\.(view|create|edit|delete)', key):
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
        resp = requests.get(
            f'{API}/api/clients/{target_client_id}/',
            headers=headers,
            timeout=10,
        )
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
        resp = requests.get(
            f'{API}/api/clients/{target_client_id}/',
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            payload = resp.json()
            app_settings = payload.get('app_settings')
            return app_settings if isinstance(app_settings, dict) else {}
    except requests.exceptions.RequestException:
        return {}
    return {}


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


def _flash(request, message, level='success'):
    """Add a flash message to the session."""
    if '_messages' not in request.session:
        request.session['_messages'] = []
    request.session['_messages'].append({'message': message, 'level': level})
    request.session.modified = True


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

    try:
        clients_resp = requests.get(f'{API}/api/clients/public/', timeout=10)
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
    except requests.exceptions.ConnectionError:
        clients_load_failed = True
        error = 'Cannot connect to backend. Start backend server on http://127.0.0.1:8000'

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
                resp = requests.post(f'{API}/api/token/', json=payload, timeout=10)
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
                    return redirect('dashboard')
                else:
                    error = 'Invalid username or password.'
            except requests.exceptions.ConnectionError:
                error = 'Cannot connect to the backend server. Is it running on port 8000?'

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
                resp = requests.post(
                    f'{API}/api/accounts/password-setup-confirm/',
                    json={'uid': uid, 'token': token, 'new_password': password},
                    timeout=10,
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


def logout_view(request):
    request.session.flush()
    return redirect('login')


# ─────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────

def dashboard(request):
    messages = _pop_messages(request)

    try:
        emp_resp = _api_get(request, '/api/employees/')
        cf_resp  = _api_get(request, '/api/custom-fields/')

        redirect_resp = _handle_unauthorized(emp_resp, request)
        if redirect_resp:
            return redirect_resp

        employees     = emp_resp.json() if emp_resp.status_code == 200 else []
        custom_fields = cf_resp.json()  if cf_resp.status_code == 200 else []

        # Handle paginated and non-paginated responses
        if isinstance(employees, dict):
            emp_count = employees.get('count', len(employees.get('results', [])))
        else:
            emp_count = len(employees)

        if isinstance(custom_fields, dict):
            cf_count = custom_fields.get('count', len(custom_fields.get('results', [])))
        else:
            cf_count = len(custom_fields)

        recent_employees = (
            employees.get('results', employees)[:5]
            if isinstance(employees, dict)
            else employees[:5]
        )

    except requests.exceptions.ConnectionError:
        emp_count = 0
        cf_count  = 0
        recent_employees = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'dashboard.html', {
        'emp_count': emp_count,
        'cf_count': cf_count,
        'recent_employees': recent_employees,
        'messages': messages,
        **_get_context(request),
    })


def policy_page(request):
    addon_redirect = _require_addon(request, 'policy')
    if addon_redirect:
        return addon_redirect
    messages = _pop_messages(request)
    return render(request, 'policy/list.html', {
        'messages': messages,
        **_get_context(request),
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

        logo_url = (request.POST.get('logo_url') or '').strip() or existing_brand.get('logo_url', '')
        favicon_url = (request.POST.get('favicon_url') or '').strip() or existing_brand.get('favicon_url', '')

        if _bool_field('remove_logo'):
            logo_url = ''
        if _bool_field('remove_favicon'):
            favicon_url = ''

        logo_file = request.FILES.get('logo_file')
        if logo_file:
            logo_url = _store_uploaded_dynamic_file(logo_file, folder='brand_assets/logo')

        favicon_file = request.FILES.get('favicon_file')
        if favicon_file:
            favicon_url = _store_uploaded_dynamic_file(favicon_file, folder='brand_assets/favicon')

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
                'theme_mode': (request.POST.get('theme_mode') or 'dark').strip().lower(),
                'font_family': (request.POST.get('font_family') or 'inter').strip().lower(),
                'font_family_custom': (request.POST.get('font_family_custom') or '').strip(),
                'font_size_base': _int_field('font_size_base', default=14, min_value=12, max_value=20),
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


def permission_list(request):
    if request.session.get('role') != 'admin':
        return render(request, 'errors/403.html', status=403)

    messages = _pop_messages(request)
    errors = []
    users = []
    permission_options = []
    groups = []

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
                            'errors': errors,
                            'messages': messages,
                            **_get_context(request),
                        })

                    target_user = next((u for u in users if str(u.get('id')) == str(profile_id)), None)
                    selected_group = next((g for g in groups if str(g.get('id')) == str(group_id)), None)
                    inferred_role = _infer_employee_role_from_group_name(
                        (selected_group or {}).get('name', '')
                    ) if selected_group else ''
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
                                    role_update_payload = {
                                        'first_name': linked_employee.get('first_name', ''),
                                        'last_name': linked_employee.get('last_name', ''),
                                        'email': linked_employee.get('email', ''),
                                        'role': inferred_role,
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
    selected_role = (request.GET.get('role') or '').strip().lower()
    params   = {}
    if search_q:
        params['search'] = search_q
    if selected_role in ('employee', 'hr', 'manager'):
        params['role'] = selected_role

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
        include_keys=['email', 'first_name', 'last_name', 'role', 'joining_date', 'hr', 'manager'],
    )
    friendly = []
    for msg in errors:
        low = str(msg).lower()
        if 'email:' in low and 'already exists' in low:
            friendly.append('An employee with this email already exists. Please use a different email address.')
        else:
            friendly.append(msg)
    return friendly


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
    hr_options = _employee_assignment_options(request, 'hr')
    manager_options = _employee_assignment_options(request, 'manager')

    form.fields['hr'].choices = [('', 'Select HR (Optional)')] + [
        (item['id'], item['label']) for item in hr_options
    ]
    form.fields['manager'].choices = [('', 'Select Manager (Optional)')] + [
        (item['id'], item['label']) for item in manager_options
    ]

    dynamic_models, dynamic_fields_by_model = _get_dynamic_models_with_fields(request)

    if request.method == 'POST':
        form = EmployeeForm(request.POST)
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
                    hr_value = employee_data.pop('hr', '')
                    manager_value = employee_data.pop('manager', '')
                    employee_data['client'] = client_id
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
                            emp_update_data['role'] = inferred_role
                    emp_update_data['client'] = client_id
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
        initial_data['hr'] = str(employee_data.get('hr') or '')
        initial_data['manager'] = str(employee_data.get('manager') or '')
        form = EmployeeForm(initial=initial_data)
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

    return render(request, 'leaves/list.html', {
        'leaves': leaves,
        'employees': employees,
        'leave_types': leave_types,
        'errors': errors,
        'messages': messages,
        'selected_status': selected_status,
        'selected_employee': selected_employee,
        'pending_count': pending_count,
        'can_view_all_leaves': can_view_all_leaves,
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

    try:
        resp = _api_get(request, '/api/dynamic-models/')
        redir = _handle_unauthorized(resp, request)
        if redir:
            return redir
        data = resp.json() if resp.status_code == 200 else []
        dynamic_models = data.get('results', data) if isinstance(data, dict) else data
    except requests.exceptions.ConnectionError:
        dynamic_models = []
        messages.append({'message': 'Backend server unreachable.', 'level': 'error'})

    return render(request, 'dynamic_models/list.html', {
        'dynamic_models': dynamic_models,
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
                today_iso = datetime.date.today().isoformat()
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

        today = datetime.date.today().isoformat()
        now_time = datetime.datetime.now().strftime('%H:%M:%S')
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
            permission_redirect = _require_module_permission(
                request,
                'attendance.create' if is_attendance_model else f'dynamic_model.{model_id}.create'
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
    current_time = datetime.datetime.now().strftime('%H:%M:%S')
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

            today = datetime.date.today().isoformat()
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
    current_time = datetime.datetime.now().strftime('%H:%M:%S')
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
