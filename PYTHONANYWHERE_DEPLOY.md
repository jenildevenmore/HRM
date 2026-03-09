# PythonAnywhere Deployment (Frontend + Backend on One Free Web App)

This project has two Django apps:
- `hrm_frontend` (UI)
- `hrm_project` (API)

On PythonAnywhere free plan, run both under one web app using one WSGI dispatcher.

## 1) Upload code

```bash
cd ~
git clone <your-repo-url> hrm_project
cd ~/hrm_project
```

## 2) Create virtualenv and install deps

```bash
mkvirtualenv --python=python3.11 hrm-env
workon hrm-env
pip install -r ~/hrm_project/requirements.txt
```

## 3) Set environment variables (Web tab -> Environment variables)

Set these for your username/domain:

- `DJANGO_DEBUG=False`
- `FRONTEND_DEBUG=False`
- `DJANGO_SECRET_KEY=<strong-secret>`
- `FRONTEND_SECRET_KEY=<strong-secret>`
- `DJANGO_ALLOWED_HOSTS=<yourusername>.pythonanywhere.com`
- `FRONTEND_ALLOWED_HOSTS=<yourusername>.pythonanywhere.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<yourusername>.pythonanywhere.com`
- `BACKEND_API_URL=https://<yourusername>.pythonanywhere.com`
- `FRONTEND_BASE_URLS=https://<yourusername>.pythonanywhere.com`
- `EMAIL_HOST_USER=<your-email>`
- `EMAIL_HOST_PASSWORD=<your-app-password>`
- `DEFAULT_FROM_EMAIL=<your-email>`

Optional cookie hardening:
- `SESSION_COOKIE_SECURE=True`
- `CSRF_COOKIE_SECURE=True`
- `FRONTEND_SESSION_COOKIE_SECURE=True`
- `FRONTEND_CSRF_COOKIE_SECURE=True`

## 4) Run migrations + collect static

```bash
workon hrm-env
cd ~/hrm_project/hrm_project
python manage.py migrate
python manage.py collectstatic --noinput

cd ~/hrm_project/hrm_frontend
python manage.py collectstatic --noinput
python manage.py check

cd ~/hrm_project/hrm_project
python manage.py check
```

## 5) Configure WSGI (single web app)

In PythonAnywhere Web tab, open your WSGI config file and replace with the content from:

- `~/hrm_project/deploy/pythonanywhere_wsgi.py`

Important:
- Replace `PA_USER = "yourusername"` with your real PythonAnywhere username.

## 6) Static files mappings (Web tab -> Static files)

Add these mappings:

1. URL: `/static/` -> Directory: `/home/<yourusername>/hrm_project/hrm_frontend/static`
2. URL: `/media/` -> Directory: `/home/<yourusername>/hrm_project/hrm_frontend/media`
3. URL: `/backend-static/` -> Directory: `/home/<yourusername>/hrm_project/hrm_project/staticfiles`

## 7) Reload web app

Click **Reload** in Web tab.

## 8) Verify routes

- Frontend: `https://<yourusername>.pythonanywhere.com/login/`
- API: `https://<yourusername>.pythonanywhere.com/api/clients/public/`
- Admin: `https://<yourusername>.pythonanywhere.com/admin/`

## Notes

- You do not need ports `8000/8001` on PythonAnywhere.
- Keep only one production domain and use HTTPS URLs in all env vars.
- If API calls fail, check PythonAnywhere **Error log** first.
