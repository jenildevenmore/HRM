"""
PythonAnywhere single-web-app dispatcher for this repository.

Serves:
- Frontend Django app on "/"
- Backend Django API app on "/api/" and "/admin/"

Copy this content into your PythonAnywhere WSGI file and update paths/usernames.
"""

import os
import sys

from django.core.wsgi import get_wsgi_application


PA_USER = "yourusername"
PROJECT_ROOT = f"/home/{PA_USER}/hrm_project"

# Ensure both Django projects are importable.
for path in [
    PROJECT_ROOT,
    f"{PROJECT_ROOT}/hrm_project",
    f"{PROJECT_ROOT}/hrm_frontend",
]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Build backend WSGI application.
os.environ["DJANGO_SETTINGS_MODULE"] = "hrm_project.settings"
backend_application = get_wsgi_application()

# Build frontend WSGI application.
os.environ["DJANGO_SETTINGS_MODULE"] = "hrm_frontend.settings"
frontend_application = get_wsgi_application()


def application(environ, start_response):
    path = environ.get("PATH_INFO", "") or ""

    # Route API and backend admin to backend project.
    if path.startswith("/api/") or path.startswith("/admin/"):
        return backend_application(environ, start_response)

    # Everything else goes to frontend project.
    return frontend_application(environ, start_response)
