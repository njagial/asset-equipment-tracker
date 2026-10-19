# Asset & Equipment Tracking System

Production-grade Django 5 + DRF + HTMX application for tracking AV/computer
equipment, consumable stock levels, and maintenance work — with generated
Code128/QR labels, camera-based scanning (html5-qrcode), role-based access
control, PostgreSQL JSONB custom fields, and Celery-driven low-stock alerts.

## Stack

| Layer      | Choice                                                        |
|------------|---------------------------------------------------------------|
| Backend    | Django 5.2, Django REST Framework, django-filter              |
| Frontend   | Server-rendered templates + HTMX, Bootstrap 5, html5-qrcode   |
| Database   | PostgreSQL 16 (JSONB, trigram fuzzy search)                    |
| Jobs       | Celery + Redis, django-celery-beat (scheduled sweeps)          |
| Packages   | `uv` (pyproject.toml + uv.lock are the source of truth)        |

## Quickstart (local, no Docker)

```bash
uv sync                          # creates .venv from the lockfile
cp .env.example .env             # optional; defaults work without Docker
uv run manage.py migrate         # sqlite dev fallback when DATABASE_URL unset
uv run manage.py createsuperuser
uv run manage.py runserver
```

Celery (alerts + scheduled sweeps) — get Redis from Docker:

```bash
docker compose up -d redis
uv run celery -A config worker -l info
uv run celery -A config beat -l info
```

## Quickstart (full stack, Docker)

```bash
cp .env.example .env
docker compose up --build        # postgres + redis + web + worker + beat
```

## Test / lint

```bash
uv run manage.py test            # Django runner (uses config.settings.test)
uv run pytest                    # equivalent, via pytest-django
uv run ruff check . && uv run ruff format --check .
```

## Roles (RBAC)

| Role       | Read | Edit metadata | Check in/out | Resolve restock | Delete / admin |
|------------|------|--------------|--------------|-----------------|----------------|
| VIEWER     | ✔    | ✖            | ✖            | ✖               | ✖              |
| TECHNICIAN | ✔    | ✔            | ✔            | ✔               | ✖              |
| ADMIN      | ✔    | ✔            | ✔            | ✔               | ✔              |

Enforced in `apps/accounts/permissions.py` (DRF) and mirrored for template views.

## URL map

- `/assets/` — HTMX searchable/paginated inventory (tag, serial, location, name)
- `/assets/<id>/` — detail, audit trail, maintenance, label links
- `/assets/<id>/label/` — printable 2"x1" label (QR + Code128)
- `/scan/` — camera scanner (html5-qrcode) → check-in/check-out
- `/consumables/` — stock list with ±adjust buttons (alerts fire on save)
- `/alerts/restock/` — low-stock restock queue
- `/maintenance/` — schedule/complete work orders (recurring support)
- `/api/` — DRF: `/api/inventory/*`, `/api/maintenance/*`

## Migration strategy

See `docs/MIGRATIONS.md` — expand/contract pattern, Postgres-only extensions
(vendor-guarded), CI invariant `makemigrations --check`, and rollback policy.
