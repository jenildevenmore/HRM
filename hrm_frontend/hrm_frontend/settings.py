from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name, default=False):
    raw = str(os.getenv(name, str(default))).strip().lower()
    return raw in ('1', 'true', 'yes', 'on')


def _env_csv(name, default=''):
    return [part.strip() for part in os.getenv(name, default).split(',') if part.strip()]


SECRET_KEY = os.getenv('FRONTEND_SECRET_KEY', 'django-frontend-secret-key-change-in-production')

DEBUG = _env_bool('FRONTEND_DEBUG', True)

ALLOWED_HOSTS = _env_csv('FRONTEND_ALLOWED_HOSTS', '127.0.0.1,localhost,192.168.1.66')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AuthRequiredMiddleware',
]

ROOT_URLCONF = 'hrm_frontend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.jinja2.Jinja2',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
        'OPTIONS': {
            'environment': 'hrm_frontend.jinja2.environment',
        },
    },
]

WSGI_APPLICATION = 'hrm_frontend.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'frontend_db.sqlite3',
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.file'
SESSION_FILE_PATH = BASE_DIR / 'sessions'
SESSION_FILE_PATH.mkdir(parents=True, exist_ok=True)

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Backend API base URL
BACKEND_API_URL = os.getenv('BACKEND_API_URL', 'https://jenilevenmore.pythonanywhere.com')

SESSION_COOKIE_SECURE = _env_bool('FRONTEND_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('FRONTEND_CSRF_COOKIE_SECURE', not DEBUG)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
