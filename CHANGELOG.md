# Changelog

All notable changes to this project are documented here, newest first.

## 2026-09-06 — Project scaffold

- Set up the Python project layout: Django-style `app/apps/<name>/` packages
  (`users`, `organizations`, `memberships`, `projects`, `tasks`, `comments`,
  `audit`), each with `models.py` / `schemas.py` / `router.py` / `services.py`.
- Added `app/core` (settings, async SQLAlchemy engine/session, Redis client)
  and `app/common` (shared `Base`, `TimestampMixin`, `UUIDPrimaryKeyMixin`).
- Wired up FastAPI in `app/main.py` with a `/health` endpoint and every app's
  router included.
- Added async-aware Alembic environment (`alembic/env.py`) that imports every
  app's `models.py` so autogenerate sees the full metadata.
- Added `docker-compose.yml` with `db` (Postgres 16), `redis` (Redis 7), and
  `api` services, all configuration driven by `.env` / `.env.example`.
- Added `pytest` + `httpx` async test setup (`tests/`), mirroring the
  `app/apps/` layout.
- Verified end-to-end: `docker compose up --build` boots cleanly, `/health`
  returns `200`, and `alembic revision --autogenerate` connects to Postgres
  and generates a migration successfully.
- See [docs/architecture.md](docs/architecture.md) for the full rationale.
