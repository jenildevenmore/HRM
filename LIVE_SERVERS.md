# HRM Multi-Server Live Document

Use this file to track all live servers for this project (AWS, Hostinger, etc.).

## 1) Master Server List

| Environment | Provider | Status | Domain/Base URL | UI | API | SSH/Panel |
|---|---|---|---|---|---|---|
| Local | Local machine | Active | `http://127.0.0.1:8000` | `/login/` | `/api/` | Local terminal |
| Staging | AWS EC2 | `TBD` | `TBD` | `/login/` | `/api/` | `ssh ubuntu@<ip>` |
| Production | Hostinger VPS | `TBD` | `TBD` | `/login/` | `/api/` | Hostinger panel + SSH |
| Backup Production | DigitalOcean Droplet | `TBD` | `TBD` | `/login/` | `/api/` | `ssh root@<ip>` |

## 2) Common Deployment Steps (Any Linux Server)

1. Pull latest code:
   - `git pull origin <branch>`
2. Activate venv and install deps:
   - `pip install -r requirements.txt`
3. Run migrations:
   - `python manage.py migrate`
4. Collect static:
   - `python manage.py collectstatic --noinput`
5. Restart app service (Gunicorn/Uvicorn/Supervisor/systemd).
6. Reload reverse proxy (Nginx/Apache).
7. Verify:
   - `<domain>/login/`
   - `<domain>/api/`
   - `<domain>/admin/`

## 3) Environment Variables (Production-Safe Baseline)

Set these on every live server with server-specific values:

- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=<server-domain>,<www-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<server-domain>,https://<www-domain>`
- `BACKEND_API_URL=https://<server-domain>`
- `FRONTEND_BASE_URLS=https://<server-domain>`
- `SESSION_COOKIE_SECURE=True`
- `CSRF_COOKIE_SECURE=True`
- `SECURE_SSL_REDIRECT=True`

## 4) Provider Sections

### AWS (EC2 + Nginx + Gunicorn + PostgreSQL)

- Server Name: `TBD`
- Region: `TBD`
- Instance Type: `TBD`
- Domain: `TBD`
- SSH: `ssh -i <key.pem> ubuntu@<public-ip>`
- App Path: `/var/www/hrm_project`
- Service Name: `gunicorn_hrm.service`
- Nginx Site File: `/etc/nginx/sites-available/hrm`
- SSL: Let's Encrypt (`certbot`)
- Last Deploy Date: `TBD`
- Owner: `TBD`

### Hostinger (VPS or Cloud Hosting)

- Server Name: `TBD`
- Plan: `TBD`
- Domain: `TBD`
- Access: Hostinger hPanel + SSH
- App Path: `TBD`
- Process Manager: `TBD` (systemd/supervisor/passenger)
- Web Server: `TBD` (Nginx/Apache)
- SSL: `TBD`
- Last Deploy Date: `TBD`
- Owner: `TBD`

### DigitalOcean (Droplet)

- Server Name: `TBD`
- Region: `TBD`
- Domain: `TBD`
- SSH: `ssh root@<droplet-ip>`
- App Path: `/opt/hrm_project` (or custom)
- Service Name: `TBD`
- Nginx Config: `/etc/nginx/sites-available/hrm`
- SSL: Let's Encrypt (`certbot`)
- Last Deploy Date: `TBD`
- Owner: `TBD`

### Any Other Provider

- Provider: `TBD`
- Server Name: `TBD`
- Domain: `TBD`
- Access Method: `TBD`
- App Path: `TBD`
- Service/Runtime: `TBD`
- Reverse Proxy: `TBD`
- SSL: `TBD`
- Last Deploy Date: `TBD`
- Owner: `TBD`

## 5) Health Checklist (Per Server)

- Login page works: `/login/`
- API works: `/api/`
- Admin works: `/admin/`
- Static files load
- Media files load
- Migrations up to date
- Email sending tested
- HTTPS certificate valid
- Error logs clean after deploy

## 6) Rollback Notes

For each live server maintain:

- Previous release/commit: `TBD`
- Rollback command: `git checkout <last-stable-tag>`
- Service restart command: `TBD`
- DB rollback plan: `TBD`

## 7) Update Rules

Update this file whenever:

- new live server is added
- domain/IP changes
- deploy flow changes
- env variables change
- SSL or reverse-proxy config changes
