# HRM Project Details

## 1. Project Overview

This HRM system is a modular Django application that provides end-to-end HR operations for client organizations.

Primary goals:
- Manage employees, roles, and permissions
- Handle leave, attendance, payroll, and policy workflows
- Store and collect documents (internal + public upload links)
- Support client-level branding, theme, and UI configuration
- Keep audit visibility using activity logs

The application serves both:
- Server-rendered frontend pages (Jinja templates)
- REST APIs (Django REST Framework)

Both run from the same codebase and server.

## 2. High-Level Architecture

- Framework: Django 5.2 + DRF
- Frontend: Jinja templates + shared CSS/JS in `static/`
- Auth: JWT for API (`/api/token/`) + session-based UI flows
- Database: PostgreSQL (default in current `settings.py`)
- Media: Uploaded files stored under `media/`
- Email: SMTP-based notifications + offer letter PDF email

Request flow:
1. Browser hits UI route in `core.urls`
2. `core.views` renders page and calls internal API helpers
3. API endpoints in app viewsets return data
4. Template renders cards/forms/tables with permission-gated modules

## 3. Major Apps and Responsibilities

- `accounts`
  - User profile and permission group APIs
  - Role metadata and module permissions

- `clients`
  - Client records, addon enablement
  - Client role definitions (`ClientRole`)

- `employees`
  - Employee CRUD
  - Auto creation/linking of login user profile
  - HR/Manager assignment support

- `leaves`
  - Leave type management
  - Leave request lifecycle (pending/approved/rejected/cancelled)
  - Day/Half-day/Hourly leave validation
  - Leave balance API (total/used/available)

- `dynamic_models`
  - Dynamic entities/fields/records
  - Attendance model and punch/auto-clockout integration points

- `payroll`
  - Payroll policy, employee compensation, payroll report calculation

- `documents`
  - Internal documents
  - Public document upload links with token URLs
  - Multi-document type collection
  - Offer letter builder and PDF mail delivery

- `holidays`, `shifts`, `banks`, `policies`
  - Operational HR module CRUD and list/search management

- `activity_logs`
  - Middleware + listing of create/update/delete/view actions

- `core`
  - UI controllers, template rendering, navigation context
  - Auth-required middleware and shared utilities

## 4. Key Data Models (Conceptual)

- Client
  - Name/domain/schema/addons/app settings/role limit

- ClientRole
  - Per-client role profile
  - Base role (`employee`, `hr`, `manager`)
  - Module permissions and addon map

- Employee
  - Core employee identity and organization mapping
  - Role + client role + HR/manager links

- LeaveType
  - Leave policy per client (max yearly days, paid/unpaid)

- LeaveRequest
  - Leave unit, dates, approval chain, comments, status
  - Supports `day`, `half_day`, `hour`

- DynamicModel / DynamicField / DynamicRecord
  - Metadata-driven module records (including attendance)

- Document / DocumentUploadRequest
  - Internal files + public upload token flows

## 5. Permissions and Visibility

Visibility is controlled by:
- User role (`superadmin`, `admin`, employee-side roles)
- Enabled addons per client/profile
- Module permission keys (e.g. `leaves.view`, `documents.create`)

Effects:
- Sidebar modules are shown/hidden dynamically
- Create/edit/delete actions are permission-gated
- Some pages show all employee data for admin/HR/manager and limited data for employees

## 6. Main Functional Workflows

### 6.1 Employee Onboarding
1. Admin opens employee module
2. Creates employee with client role
3. System creates/links login user and profile
4. Password setup email can be sent

### 6.2 Leave Application and Approval
1. User submits leave request with leave unit
2. Validation applies based on unit:
   - Half-day requires slot
   - Hourly requires start time and max 3 hours
3. Approval chain depends on requester role and assigned approvers
4. Approved leave contributes to leave balance used amount

### 6.3 Leave Balance
- API computes per employee x leave type:
  - total
  - used
  - available
- UI renders card per employee and table of leave types

### 6.4 Document Collection via Public Link
1. Admin creates upload request with requested document types
2. User opens tokenized upload URL
3. User submits one or more documents with mapped type
4. Records appear in document list for review/edit/open

### 6.5 Offer Letter PDF Send
1. Admin enters candidate, CTC, component percentages
2. System computes breakup, creates PDF bytes
3. PDF is attached and emailed to recipient

## 7. UI Design and Navigation Patterns

- Most modules follow a consistent pattern:
  - top heading and subtitle
  - section-toggle buttons (Create/List/Search)
  - card-based forms
  - table view for records

- Current theming supports light mode and configurable branding:
  - brand logo and name
  - sidebar logo
  - per-module sidebar icons
  - font and base size

## 8. API Surface Summary

Important routes:
- Auth:
  - `POST /api/token/`
  - `POST /api/token/refresh/`
- HR domain:
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
  - `/api/document-upload/<token>/`
  - `/api/activity-logs/`
- Dynamic:
  - `/api/dynamic-models/`
  - `/api/dynamic-fields/`
  - `/api/dynamic-records/`

## 9. Configuration and Environment

Key runtime configuration in `.env`:
- Django secret/debug/hosts/csrf
- PostgreSQL connection
- Static/media paths
- SMTP mail setup
- Backend/frontend base URLs

Current defaults expect PostgreSQL on localhost:5433.

## 10. Deployment Notes

Recommended production stack:
- Gunicorn (or uWSGI)
- Nginx reverse proxy
- PostgreSQL managed service/local instance
- HTTPS + secure cookie settings enabled

Before production:
- Set `DJANGO_DEBUG=False`
- Set strong `DJANGO_SECRET_KEY`
- Restrict `DJANGO_ALLOWED_HOSTS`
- Configure real SMTP credentials
- Run `collectstatic`

## 11. Known Extension Areas

- Deeper attendance template versioning (v1/v2)
- Reporting exports and BI summaries
- Fine-grained approval matrix editor
- Better cache and pagination for very large datasets
- Automated tests for cross-module regressions

## 12. Current Project Status Summary

Implemented and working in current codebase:
- Module-level CRUD across HR operations
- Unified UI style and module tabs
- First-login organization setup support
- Public document upload with typed documents
- Leave unit enhancements (hourly/half-day)
- Dashboard with clickable cards and quick actions
- Settings-driven branding and module icons

This document can be treated as the functional baseline for your next version planning.
