# One Project Run Mode (Frontend + Backend from `hrm_project/manage.py`)

You can now run both UI and API from one Django project.

## What changed

- Backend project (`hrm_project`) now mounts frontend routes from `core.urls`.
- API remains under `/api/...`.
- Jinja templates are loaded from `hrm_frontend/templates`.
- Frontend static/media are served from `hrm_frontend/static` and `hrm_frontend/media`.

## Run locally

```bash
cd C:\hrm_project\hrm_project
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Use:
- UI: `http://127.0.0.1:8000/login/`
- API: `http://127.0.0.1:8000/api/`

## Required env variables (recommended)

- `BACKEND_API_URL=http://127.0.0.1:8000`
- `FRONTEND_BASE_URLS=http://127.0.0.1:8000`

For production set your real domain.
