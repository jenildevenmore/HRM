# HRM Project

End-to-end HRM (Human Resource Management) platform built with Django and Django REST Framework.
The project serves both:

- Server-rendered web UI (Jinja templates)
- REST APIs (`/api/...`)

Both run from one Django project.

## Table of Contents

- Overview
- Tech Stack
- Features
- Project Structure
- Prerequisites
- Quick Start (Local)
- Environment Variables
- Database Notes
- Running the Application
- API Overview
- Common Management Commands
- Deployment Notes
- Troubleshooting
- Related Docs

## Overview

This repository provides a modular HRM system with role-based access, client-level configuration, and operational modules such as employee management, leave workflows, payroll configuration, documents, and activity logging.

## Tech Stack

- Python 3.10+
- Django 5.2.12
- Django REST Framework 3.16.1
- Jinja2 templates
- JWT auth (`djangorestframework-simplejwt`)
- `django-filter`
- ReportLab (PDF generation)
- PostgreSQL (current active DB configuration in settings)

## Features

- Authentication and profile management
- Client and role management
- Employee lifecycle management
- Leave types, requests, balance, approval flows
- Dynamic model/field/record engine
- Attendance auto clock-out trigger endpoint
- Payroll policy, compensation, and payroll report APIs
- Document management + public tokenized upload links
- Offer letter PDF generation and email sending
- Holiday, shift, bank, and company policy modules
- Activity logging
- UI branding/theming settings

## Project Structure

```text
c:\hrm_project
+-- hrm_project\
|   +-- manage.py
|   +-- hrm_project\          # settings.py, urls.py, wsgi.py
|   +-- core\                 # UI routes/views/templates context
|   +-- accounts\
|   +-- clients\
|   +-- employees\
|   +-- leaves\
|   +-- payroll\
|   +-- documents\
|   +-- dynamic_models\
|   +-- ...other apps
|   +-- templates\
|   +-- static\
|   \-- media\
+-- deploy\
+-- postman\
+-- requirements.txt
+-- .env
\-- LIVE_SERVERS.md
```

## Prerequisites

- Python 3.10 or newer
- pip
- Virtual environment support (`venv`)
- PostgreSQL (if using current default DB config)

## Quick Start (Local)

1. Create virtual environment:

```powershell
cd C:\hrm_project
python -m venv .venv
```

2. Activate virtual environment:

```powershell
.\.venv\Scripts\activate
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Configure `.env` in project root (`C:\hrm_project\.env`).

5. Run migrations:

```powershell
cd C:\hrm_project\hrm_project
..\ .venv\Scripts\python.exe manage.py migrate
```

6. Start server:

```powershell
..\ .venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Open:

- UI: `http://127.0.0.1:8000/login/`
- API: `http://127.0.0.1:8000/api/`
- Admin: `http://127.0.0.1:8000/admin/`

If the venv path command fails in your shell:

```powershell
python manage.py runserver
```

## Environment Variables

Create/update `.env` with values for your environment.

### Core / Security

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DEMO_MODE`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_TIME_ZONE`

### Database (PostgreSQL active)

- `DJANGO_PG_NAME`
- `DJANGO_PG_USER`
- `DJANGO_PG_PASSWORD`
- `DJANGO_PG_HOST`
- `DJANGO_PG_PORT`

### Static / Media

- `DJANGO_STATIC_URL`
- `DJANGO_STATIC_ROOT`
- `DJANGO_MEDIA_URL`
- `DJANGO_MEDIA_ROOT`

### Email

- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

### App URLs and Runtime Flags

- `BACKEND_API_URL`
- `USE_INTERNAL_API`
- `FRONTEND_BASE_URLS`
- `FRONTEND_BASE_URL`
- `CLIENT_EXECUTION_SECRET_KEY`
  - Used as one-time activation key per client (consumed after first valid use).

### HTTPS / Cookies

- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SECURE_SSL_REDIRECT`

### Demo Mode

- Set `DEMO_MODE=True` to disable create/update/delete operations in both UI and API.
- Users can still click actions and navigate, but writes are blocked with a demo message.

## Database Notes

Current `hrm_project/settings.py` uses PostgreSQL configuration directly.

- The SQLite fallback block exists but is currently commented out.
- If you want SQLite locally, either:
1. uncomment and use the `DJANGO_DB_ENGINE` switch logic in `settings.py`, or
2. manually change `DATABASES` to `django.db.backends.sqlite3`.

## Running the Application

The project is in unified mode:

- UI routes are served by `core.urls`
- API routes are served under `/api/` from DRF router and custom endpoints

Key UI routes:

- `/login/`
- `/`
- `/employees/`
- `/leaves/`
- `/documents/`
- `/settings/`

## API Overview

Auth:

- `POST /api/token/`
- `POST /api/token/refresh/`

Main resources:

- `/api/accounts/`
- `/api/account-groups/`
- `/api/clients/`
- `/api/client-roles/`
- `/api/employees/`
- `/api/custom-fields/`
- `/api/custom-field-values/`
- `/api/dynamic-models/`
- `/api/dynamic-fields/`
- `/api/dynamic-records/`
- `/api/leaves/`
- `/api/leave-types/`
- `/api/holidays/`
- `/api/shifts/`
- `/api/bank-accounts/`
- `/api/payroll-policy/`
- `/api/employee-compensation/`
- `/api/company-policies/`
- `/api/documents/`
- `/api/document-upload-requests/`
- `/api/activity-logs/`

Custom endpoints:

- `GET /api/leave-balance/`
- `GET /api/payroll-report/`
- `POST /api/attendance/auto-clockout/run/`
- `POST /api/document-upload/<uuid:token>/`

## Common Management Commands

Run these from `C:\hrm_project\hrm_project`:

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py check
```

## Deployment Notes

For live server tracking and provider-specific details (AWS/Hostinger/etc.), use:

- `LIVE_SERVERS.md`

Production baseline:

- `DJANGO_DEBUG=False`
- restricted `DJANGO_ALLOWED_HOSTS`
- correct `DJANGO_CSRF_TRUSTED_ORIGINS` with HTTPS domains
- secure cookie flags enabled
- static collection completed

## Troubleshooting

Missing package errors:

```powershell
pip install -r requirements.txt
```

Database connection issues:

- Verify PostgreSQL is running and reachable.
- Recheck `DJANGO_PG_*` values.

Static/media not loading:

- Confirm `DJANGO_STATIC_ROOT` and `DJANGO_MEDIA_ROOT`.
- Run `collectstatic` for production.

Email not sending:

- Verify SMTP credentials and host/port/TLS.
- Use app password where required (for Gmail SMTP).

## Related Docs

- `PROJECT_DETAILS.md` - functional and architecture notes
- `ONE_PROJECT_RUN.md` - unified run mode note
- `LIVE_SERVERS.md` - multi-provider live server documentation
- `PYTHONANYWHERE_DEPLOY.md` - legacy/optional provider-specific deployment reference
- `CLIENT_ZIP_DELIVERY_GUIDE.md` - customer handover guide for ZIP-based delivery + activation key
- `HRM_USER_MANUAL.html` - ready-to-share user manual web page (WorkDo-style layout)
