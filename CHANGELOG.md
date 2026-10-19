# Changelog

All notable changes to the **Asset & Equipment Tracking System** are documented
in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Comprehensive test suite (69 tests, pytest-django on the SQLite in-memory
  test settings) covering:
  - **accounts**: role rank boundaries, `is_admin_role`, anonymous denial for
    both the `min_role` web helper and the DRF `RolePermission` classes.
  - **inventory**: DRF API RBAC (read for any authenticated role, write
    admin-only), `search` / `status` / `below_threshold` filters, pagination,
    read-only transaction audit endpoint; HTMX web flows for check-out,
    check-in, set-status and HTMX error partials; label / QR / Code128
    endpoints; consumable ±adjust clamping and low-only list filter;
    category/consumable create; scanner lookup (known and unknown codes); and
    auto-tag sequencing.
  - **maintenance**: web list filters (status / type / upcoming), create and
    complete flows (regular + HTMX), recurrence-interval validation,
    `is_due` property, DRF API RBAC, serializer date-order validation,
    filterset + ordering, and the "nothing due" notify task path.
  - **alerts**: low-stock snapshot semantics (min-quantity updates, one open
    alert per consumable), notify task skip for missing/resolved alerts,
    email channel contents, and sweep idempotency report counts.
- `CHANGELOG.md` (this file).

## [0.1.0] - 2026-10-19

### Added

- Initial scaffold: Django 5.2 + DRF + HTMX application for tracking AV and
  computer equipment, consumable stock, and maintenance work.
- RBAC with `ADMIN` / `TECHNICIAN` / `VIEWER` roles enforced through DRF
  permission classes and mirrored `min_role` template-view guards.
- Inventory domain: assets (audit trail, JSONB custom fields, fuzzy search),
  consumables, category management (PostgreSQL pg_trgm aware with a SQLite
  fallback for dev/tests).
- Labels: printable 2"x1" label view with generated QR (Pillow) and Code128
  (python-barcode) plus dedicated SVG/PNG endpoints and
  html5-qrcode camera scan page.
- Maintenance: scheduled/recurring work orders with completion staging of the
  next occurrence and due-date email notifications.
- Alerts: low-stock signal pipeline, single-open-alert constraint, resolve
  endpoint on the restock queue, email + Slack notification channels, and a
  15-minute Celery sweep backstop.
- Celery infrastructure (worker + beat schedules for low-stock sweeps and
  due-maintenance notification), docker-compose full-stack deployment,
  expand/contract migration strategy documented in `docs/MIGRATIONS.md`.

[Unreleased]: https://github.com/njagial/asset-equipment-tracker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/njagial/asset-equipment-tracker/releases/tag/v0.1.0
