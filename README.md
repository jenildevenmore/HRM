# HRM Project

A full-stack HRM (Human Resource Management) system built with Django + DRF, Jinja templates, and a modular addon/permission model.

This project runs UI and API in one Django app.

## Tech Stack

- Python 3.10+
- Django 5.2
- Django REST Framework
- Jinja2 templates
- JWT auth (`djangorestframework-simplejwt`)
- PostgreSQL (default in current settings)

## Core Modules

- Authentication and user profiles
- Client management (multi-client, roles, addon toggles)
- Employee management
- Leave management
  - Leave types
  - Leave applications (Day / Half Day / Hourly)
  - Leave balance per employee
- Attendance (dynamic model driven)
- Payroll
- Documents
  - Internal document list
  - Public upload links
  - Multi-document upload support
  - Offer-letter PDF generation + email send
- Holidays
- Shifts
- Bank accounts
- Company policies
- Activity logs
- Import / Export
- Settings (branding, theme, sidebar logo/icons)

## Project Structure

```text
c:\hrm_project
+-- hrm_project\                # Django project root (run manage.py here)
|   +-- manage.py
|   +-- hrm_project\            # settings, urls, wsgi, jinja env
|   +-- core\                   # frontend routes + page controllers
|   +-- accounts\
|   +-- clients\
|   +-- employees\
|   +-- leaves\
|   +-- payroll\
|   +-- documents\
|   +-- ... other apps
|   +-- templates\
|   +-- static\
|   \-- media\
+-- requirements.txt
\-- .env
```

## Installation

1. Create and activate virtual environment:

```powershell
cd c:\hrm_project
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Environment Variables

Create/update `.env` in `c:\hrm_project\`.

### Django / Security

- `DJANGO_SECRET_KEY=...`
- `DJANGO_DEBUG=True`
- `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`
- `DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000`
- `DJANGO_TIME_ZONE=Asia/Kolkata`

### Database (current default: PostgreSQL)

- `DJANGO_PG_NAME=HRM`
- `DJANGO_PG_USER=admin`
- `DJANGO_PG_PASSWORD=admin`
- `DJANGO_PG_HOST=localhost`
- `DJANGO_PG_PORT=5433`

### Static / Media

- `DJANGO_STATIC_URL=/static/`
- `DJANGO_STATIC_ROOT=...` (optional)
- `DJANGO_MEDIA_URL=/media/`
- `DJANGO_MEDIA_ROOT=...` (optional)

### Email

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST=smtp.gmail.com`
- `EMAIL_PORT=587`
- `EMAIL_USE_TLS=True`
- `EMAIL_HOST_USER=...`
- `EMAIL_HOST_PASSWORD=...`
- `DEFAULT_FROM_EMAIL=...`

### Internal API + Frontend URL

- `BACKEND_API_URL=http://127.0.0.1:8000`
- `USE_INTERNAL_API=True`
- `FRONTEND_BASE_URLS=http://127.0.0.1:8000`

## Run the Project

```powershell
cd c:\hrm_project\hrm_project
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Use:

- UI: `http://127.0.0.1:8000/login/`
- API root: `http://127.0.0.1:8000/api/`

If venv-relative command fails in your shell, use:

```powershell
python manage.py runserver
```

## API Endpoints (Main)

- Auth
  - `POST /api/token/`
  - `POST /api/token/refresh/`
- Accounts / Roles
  - `/api/accounts/`
  - `/api/account-groups/`
  - `/api/clients/`
  - `/api/client-roles/`
- HR Modules
  - `/api/employees/`
  - `/api/leaves/`
  - `/api/leave-types/`
  - `/api/leave-balance/`
  - `/api/holidays/`
  - `/api/shifts/`
  - `/api/bank-accounts/`
  - `/api/payroll-policy/`
  - `/api/employee-compensation/`
  - `/api/payroll-report/`
  - `/api/company-policies/`
  - `/api/documents/`
  - `/api/document-upload-requests/`
  - `/api/document-upload/<uuid:token>/`
  - `/api/activity-logs/`
- Dynamic Models
  - `/api/dynamic-models/`
  - `/api/dynamic-fields/`
  - `/api/dynamic-records/`
  - `/api/attendance/auto-clockout/run/`

## Permissions and Addons

- Module visibility is controlled via:
  - enabled addons
  - module permissions
  - role (`superadmin`, `admin`, employee roles)
- Sidebar/menu items are dynamic from addon + permission context.

## Leave Rules Implemented

- Leave unit options: `day`, `half_day`, `hour`
- Half day requires slot: `first_half` / `second_half`
- Hourly leave:
  - max 3 hours/day
  - start time required
  - end time auto-calculated from selected leave hours
- Past-date leave requests blocked in serializer validation.

## Documents / Offer Letter

- Public upload links support required document types.
- Multi-document uploads supported through requested type mapping.
- Offer letter builder can generate PDF and send by email directly to employee.

## Theming and Branding

Available via settings UI:

- Light/system theme behavior
- Brand name/logo/favicon
- Sidebar logo
- Per-module sidebar icons
- Font family and base font size

## Common Commands

```powershell
# create migrations
python manage.py makemigrations

# apply migrations
python manage.py migrate

# create admin user
python manage.py createsuperuser

# collect static (production)
python manage.py collectstatic --noinput
```

## Troubleshooting

### ModuleNotFoundError: django_filters

Install dependencies in active venv:

```powershell
pip install -r requirements.txt
```

### Database connection issue

- Verify PostgreSQL is running on configured host/port.
- Check `.env` values for `DJANGO_PG_*`.

### Static/media not loading

- In dev, keep `DEBUG=True`.
- Ensure `static/` and `media/` paths are valid in settings.

### Email not sending

- Verify SMTP credentials.
- For Gmail, use app password and allow SMTP access.

## Notes

- Current settings file is configured for PostgreSQL by default.
- If you want SQLite locally, update `DATABASES` in `hrm_project/settings.py` accordingly.
