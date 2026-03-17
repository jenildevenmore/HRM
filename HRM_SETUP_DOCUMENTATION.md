# HRM Setup Documentation

This document provides a complete setup guide for the HRM project, similar to a product installation manual. It is intended for developers, deployment engineers, and clients who need to install and run the system locally or on a live server.

## 1. Introduction

The HRM Project is a Django-based Human Resource Management platform that combines:

- Web UI for HR operations
- REST APIs for system integration
- Role-based access and client-level configuration
- Modules for employees, leave, payroll, documents, attendance, and settings

The application runs as a single Django project and serves both frontend pages and backend APIs.

## 2. Technology Stack

- Python 3.10+
- Django 5.2.12
- Django REST Framework 3.16.1
- PostgreSQL
- Jinja2 templates
- ReportLab for PDF generation
- JWT authentication for API access

## 3. System Requirements

Minimum recommended environment:

- OS: Windows 10/11, Ubuntu 22.04+, or any modern Linux server
- Python: 3.10 or above
- pip: latest recommended
- Database: PostgreSQL 13+ recommended
- RAM: 4 GB minimum
- Disk Space: 2 GB minimum for app, logs, and uploads

For production:

- Nginx or Apache as reverse proxy
- Gunicorn or another WSGI server
- HTTPS-enabled domain
- SMTP account for email features

## 4. Project Structure

```text
c:\hrm_project
+-- hrm_project\
|   +-- manage.py
|   +-- hrm_project\          # settings.py, urls.py, wsgi.py
|   +-- accounts\
|   +-- clients\
|   +-- employees\
|   +-- leaves\
|   +-- payroll\
|   +-- documents\
|   +-- dynamic_models\
|   +-- templates\
|   +-- static\
|   \-- media\
+-- deploy\
+-- postman\
+-- requirements.txt
+-- .env
\-- HRM_SETUP_DOCUMENTATION.md
```

## 5. Key URLs After Setup

When the server is running locally:

- Login page: `http://127.0.0.1:8000/login/`
- Dashboard: `http://127.0.0.1:8000/`
- Admin panel: `http://127.0.0.1:8000/admin/`
- API root: `http://127.0.0.1:8000/api/`
- JWT login endpoint: `http://127.0.0.1:8000/api/token/`

## 6. Installation Guide

### 6.1 Clone or Copy the Project

Place the project in your preferred folder, for example:

```powershell
cd C:\
git clone <your-repository-url> hrm_project
cd C:\hrm_project
```

If the project is already shared as a ZIP, extract it to `C:\hrm_project`.

### 6.2 Create a Virtual Environment

```powershell
cd C:\hrm_project
python -m venv .venv
```

Activate it on Windows:

```powershell
.\.venv\Scripts\activate
```

Activate it on Linux:

```bash
source .venv/bin/activate
```

### 6.3 Install Dependencies

```powershell
pip install -r requirements.txt
```

Important:

- The project uses PostgreSQL in the active settings configuration.
- The current `requirements.txt` does not include a PostgreSQL adapter package.
- Install `psycopg[binary]` or `psycopg2-binary` in the environment before running migrations if it is not already available.

## 7. Environment Configuration

Create or update the `.env` file in the project root:

`c:\hrm_project\.env`

Use the following values as a setup template.

```env
DJANGO_SECRET_KEY=change-this-to-a-secure-value
DJANGO_DEBUG=True
DEMO_MODE=False
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
DJANGO_TIME_ZONE=Asia/Kolkata

DJANGO_PG_NAME=HRM
DJANGO_PG_USER=postgres
DJANGO_PG_PASSWORD=postgres
DJANGO_PG_HOST=localhost
DJANGO_PG_PORT=5432

DJANGO_STATIC_URL=/static/
DJANGO_STATIC_ROOT=
DJANGO_MEDIA_URL=/media/
DJANGO_MEDIA_ROOT=

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=

BACKEND_API_URL=http://127.0.0.1:8000
USE_INTERNAL_API=True
FRONTEND_BASE_URLS=http://127.0.0.1:8000
FRONTEND_BASE_URL=http://127.0.0.1:8000
CLIENT_EXECUTION_SECRET_KEY=

SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_SSL_REDIRECT=False
```

Notes:

- In the current codebase, PostgreSQL is the active database engine.
- The default port in `settings.py` is `5433` if you do not define `DJANGO_PG_PORT`.
- Set your actual PostgreSQL values before running migrations.
- For production, set `DJANGO_DEBUG=False`.

## 8. Database Setup

### 8.1 Create PostgreSQL Database

Create a database manually in PostgreSQL. Example:

```sql
CREATE DATABASE HRM;
CREATE USER hrm_user WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE HRM TO hrm_user;
```

Then update `.env`:

```env
DJANGO_PG_NAME=HRM
DJANGO_PG_USER=hrm_user
DJANGO_PG_PASSWORD=strong-password
DJANGO_PG_HOST=localhost
DJANGO_PG_PORT=5432
```

### 8.2 Run Migrations

Run commands from the Django project folder:

```powershell
cd C:\hrm_project\hrm_project
..\.venv\Scripts\python.exe manage.py migrate
```

If your shell does not accept that path style, activate the virtual environment first and run:

```powershell
cd C:\hrm_project\hrm_project
python manage.py migrate
```

### 8.3 Optional: Create Admin User

```powershell
python manage.py createsuperuser
```

This user can access:

- `/admin/`
- system-wide Django administration

## 9. Running the Application

Start the development server:

```powershell
cd C:\hrm_project\hrm_project
python manage.py runserver 0.0.0.0:8000
```

Open in browser:

- `http://127.0.0.1:8000/login/`
- `http://127.0.0.1:8000/api/`
- `http://127.0.0.1:8000/admin/`

## 10. First-Time Application Setup

After the project starts successfully, the common first-time setup flow is:

1. Create a superuser using `createsuperuser`
2. Log in to Django admin or the HRM UI
3. Create a client/company record
4. Create user roles and permission groups
5. Add employees and assign roles
6. Configure leave types, holidays, shifts, banks, payroll, and documents

There is also an onboarding route available in the UI:

- `/onboarding/setup-org/`

## 11. Create a Client Admin from Command Line

The project includes a helper command to create a client-specific admin user.

Example:

```powershell
python manage.py create_client_admin --username admin1 --password StrongPass123 --email admin@example.com --client-id 1
```

This command:

- creates a Django user
- links that user to a client
- assigns the role `admin`

## 12. Important API Endpoints

Authentication:

- `POST /api/token/`
- `POST /api/token/refresh/`

Main HR modules:

- `/api/clients/`
- `/api/client-roles/`
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
- `/api/documents/`
- `/api/document-upload-requests/`
- `/api/activity-logs/`
- `/api/dynamic-models/`
- `/api/dynamic-fields/`
- `/api/dynamic-records/`

Public upload endpoint:

- `POST /api/document-upload/<uuid:token>/`

## 13. Production Deployment Checklist

Before going live:

- Set `DJANGO_DEBUG=False`
- Set a strong `DJANGO_SECRET_KEY`
- Set real domain names in `DJANGO_ALLOWED_HOSTS`
- Set HTTPS domains in `DJANGO_CSRF_TRUSTED_ORIGINS`
- Set `SESSION_COOKIE_SECURE=True`
- Set `CSRF_COOKIE_SECURE=True`
- Set `SECURE_SSL_REDIRECT=True`
- Configure valid SMTP credentials
- Run `collectstatic`
- Serve media files correctly
- Place Gunicorn behind Nginx or Apache

Collect static files:

```powershell
python manage.py collectstatic --noinput
```

## 14. Common Commands

```powershell
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

## 15. Troubleshooting

### 15.1 Database Connection Error

Check:

- PostgreSQL service is running
- database name, username, password, host, and port are correct
- your `.env` values match the real database

### 15.2 Static Files Not Loading

Check:

- `DJANGO_STATIC_URL`
- `DJANGO_STATIC_ROOT`
- web server static file mapping in production
- `collectstatic` has been executed

### 15.3 Media Files Not Opening

Check:

- `DJANGO_MEDIA_URL`
- `DJANGO_MEDIA_ROOT`
- media path permissions on the server

### 15.4 Email Not Sending

Check:

- SMTP host and port
- TLS setting
- email username and password
- provider-specific app password if using Gmail

### 15.5 Login or Permission Issue

Check:

- the user exists
- the user has an attached profile/client mapping
- the user has the correct role and permission group

## 16. Related Project Documents

- `README.md` for general project overview
- `PROJECT_DETAILS.md` for architecture and module notes
- `ONE_PROJECT_RUN.md` for single-project run mode
- `LIVE_SERVERS.md` for production server tracking
- `PYTHONANYWHERE_DEPLOY.md` for provider-specific notes
- `CLIENT_ZIP_DELIVERY_GUIDE.md` for customer handover flow
- `HRM_USER_MANUAL.html` for end-user documentation

## 17. Final Notes

This project is already structured to run frontend and backend together from one Django application. Unlike browser-based installers, setup here is command-line driven:

- configure `.env`
- prepare PostgreSQL
- run migrations
- create admin users
- start the server

If you want, this document can also be converted into:

- a branded HTML documentation page
- a client delivery PDF
- a shorter installer guide with screenshots
