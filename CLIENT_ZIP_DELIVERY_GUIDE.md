# Client ZIP Delivery Guide

Use this guide when a client purchases your code and you deliver a ZIP package (without Git access).

## 1) What You Deliver to Client

Send these items:

1. `hrm_project_release.zip` (project code)
2. `requirements.txt`
3. `.env.template` (no secrets)
4. This guide (`CLIENT_ZIP_DELIVERY_GUIDE.md`)
5. One-time activation key for that client

Do not share your own `.env`, production DB dump, or private keys.

## 2) ZIP Package Structure

Client should extract to a folder like:

```text
C:\hrm_project
+-- hrm_project\
+-- requirements.txt
+-- manage.py (inside hrm_project folder)
+-- templates/static/apps
+-- CLIENT_ZIP_DELIVERY_GUIDE.md
```

## 3) Client Machine Prerequisites

- Python 3.10+
- PostgreSQL (or SQLite if they switch DB config)
- Internet to install Python packages

## 4) Client Setup Steps

From extracted root:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cd .\hrm_project
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Open:
- `http://127.0.0.1:8000/login/`

## 5) .env Configuration (Required)

Client must create `C:\hrm_project\.env`.

Minimum values:

```dotenv
DJANGO_SECRET_KEY=replace-with-strong-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,<client-domain>
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,https://<client-domain>
DJANGO_TIME_ZONE=Asia/Kolkata

DJANGO_PG_NAME=HRM
DJANGO_PG_USER=admin
DJANGO_PG_PASSWORD=admin
DJANGO_PG_HOST=localhost
DJANGO_PG_PORT=5433

BACKEND_API_URL=http://127.0.0.1:8000
USE_INTERNAL_API=True
FRONTEND_BASE_URLS=http://127.0.0.1:8000
FRONTEND_BASE_URL=http://127.0.0.1:8000

# One-time activation key from seller (MANDATORY)
CLIENT_EXECUTION_SECRET_KEY=<key-you-gave-client>
```

## 6) One-Time Activation Key Flow

Your project is configured so each client key is one-time usable:

1. Client puts `CLIENT_EXECUTION_SECRET_KEY` in `.env`
2. Client starts app and logs in
3. On first valid use, key is consumed and activation is locked for that client
4. Reusing same key again will not activate another client

Important:
- Keep the key private
- Do not send the same key to multiple customers

## 7) Post-Install Verification Checklist

- `/login/` opens
- Admin can log in
- Dashboard opens
- API opens at `/api/`
- Create one sample employee record
- Static files are loading

## 8) Recommended Handover Notes to Client

Share this with every buyer:

- "This license key is one-time activation only."
- "Do not remove your `.env` after activation."
- "Do not share your activation key publicly."
- "For server/domain changes, contact us for a new activation key if needed."

## 9) Seller Internal Checklist (Before Sending ZIP)

1. Remove local-only files: `.venv`, `__pycache__`, logs, temp files
2. Ensure migrations are included
3. Confirm `requirements.txt` is up to date
4. Include `.env.template` (no secrets)
5. Generate and record client activation key in your CRM/spreadsheet
6. Send ZIP + key via secure channel

---

If you want, you can create a separate guide version for Linux VPS clients (Ubuntu + Gunicorn + Nginx).

## 10) Linux VPS Setup (Ubuntu + Gunicorn + Nginx)

Use this when client wants production deployment on Ubuntu VPS.

### 10.1 Server prerequisites

- Ubuntu 22.04+ VPS
- Domain pointing to VPS public IP
- SSH access with sudo user

### 10.2 Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql postgresql-contrib
```

### 10.3 Upload and extract ZIP

```bash
sudo mkdir -p /var/www/hrm_project
sudo chown -R $USER:$USER /var/www/hrm_project
cd /var/www/hrm_project
unzip hrm_project_release.zip
```

Expected project app path:
- `/var/www/hrm_project/hrm_project`

### 10.4 Python environment and dependencies

```bash
cd /var/www/hrm_project
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 10.5 Create `.env`

Create `/var/www/hrm_project/.env` with production values:

```dotenv
DJANGO_SECRET_KEY=replace-with-strong-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<client-domain>,www.<client-domain>,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://<client-domain>,https://www.<client-domain>
DJANGO_TIME_ZONE=Asia/Kolkata

DJANGO_PG_NAME=HRM
DJANGO_PG_USER=admin
DJANGO_PG_PASSWORD=admin
DJANGO_PG_HOST=localhost
DJANGO_PG_PORT=5433

BACKEND_API_URL=https://<client-domain>
USE_INTERNAL_API=True
FRONTEND_BASE_URLS=https://<client-domain>
FRONTEND_BASE_URL=https://<client-domain>

SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True

# One-time activation key from seller
CLIENT_EXECUTION_SECRET_KEY=<key-you-gave-client>
```

### 10.6 Database migrate + static

```bash
cd /var/www/hrm_project/hrm_project
source ../.venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### 10.7 Configure Gunicorn (systemd)

Create `/etc/systemd/system/gunicorn_hrm.service`:

```ini
[Unit]
Description=Gunicorn service for HRM
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/hrm_project/hrm_project
EnvironmentFile=/var/www/hrm_project/.env
ExecStart=/var/www/hrm_project/.venv/bin/gunicorn hrm_project.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
sudo chown -R www-data:www-data /var/www/hrm_project
sudo systemctl daemon-reload
sudo systemctl enable gunicorn_hrm
sudo systemctl start gunicorn_hrm
sudo systemctl status gunicorn_hrm
```

### 10.8 Configure Nginx reverse proxy

Create `/etc/nginx/sites-available/hrm`:

```nginx
server {
    listen 80;
    server_name <client-domain> www.<client-domain>;

    client_max_body_size 50M;

    location /static/ {
        alias /var/www/hrm_project/hrm_project/staticfiles/;
    }

    location /media/ {
        alias /var/www/hrm_project/hrm_project/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/hrm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 10.9 Enable HTTPS (Let’s Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <client-domain> -d www.<client-domain>
```

### 10.10 Linux production checks

- `https://<client-domain>/login/` opens
- `https://<client-domain>/api/` opens
- Gunicorn running: `sudo systemctl status gunicorn_hrm`
- Nginx running: `sudo systemctl status nginx`
- App logs:
  - `sudo journalctl -u gunicorn_hrm -f`
  - `sudo tail -f /var/log/nginx/error.log`
