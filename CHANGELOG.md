# Changelog

All notable changes to this project are documented here, newest first.

## 2026-09-06 — Authentication, JWTs, Google OAuth, and RBAC permissions

- Added `users` (`User`, `OAuthAccount`) and `memberships` (`Membership`,
  `OrgRole`) models, plus `organizations` (`Organization`), wired together
  with SQLAlchemy relationships (cross-app forward refs via `TYPE_CHECKING`
  to avoid circular imports) and a first Alembic migration
  (`add_users_organizations_memberships`).
- Added a dedicated `auth` app (`app/apps/auth/`) with `/auth/register`,
  `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, and Google's
  `/auth/google/login` + `/auth/google/callback` (backend-driven
  Authorization Code flow).
- JWT access (15 min) + refresh (30 day) token pairs, signed HS256.
  Refresh tokens are tracked in Redis by `jti` for revocation and are
  rotated (single-use) on every `/auth/refresh` call.
- Passwords hashed with `bcrypt`. Google sign-in links to an existing
  account by verified email, or creates a new password-less one.
- Added `app/core/permissions.py`: `require_role(OrgRole.X)`, a reusable
  FastAPI dependency factory that gates any router/route on the caller's
  role (read from the `X-Org-Id` header) in one line, plus
  `require_superuser` for platform-level endpoints.
- Added `app/core/model_registry.py` (single source of truth for "import
  every app's models", shared by `app/main.py` and `alembic/env.py`).
- Tests: `tests/apps/auth/test_auth_flow.py` (integration, real DB/Redis)
  and `tests/test_permissions.py` (unit test of the role-rank check).
- Verified end-to-end against the running Docker stack: full
  register/login/refresh-rotation/logout flow via curl and pytest, Alembic
  autogenerate + upgrade, `ruff check` clean.
- See [docs/authentication.md](docs/authentication.md) for the full flow.

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
