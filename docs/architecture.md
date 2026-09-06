# Architecture

## Stack

- **Framework**: FastAPI (async)
- **ORM**: SQLAlchemy 2.0 (async, `asyncpg` driver)
- **Migrations**: Alembic (async-aware `env.py`)
- **Database**: PostgreSQL 16
- **Cache / ephemeral state**: Redis 7
- **Runtime**: Docker Compose (`db`, `redis`, `api` services)

Alembic is used instead of Django's built-in migrations, so the project is
structured FastAPI-first rather than as an actual Django project — but the
app layout intentionally mirrors Django's "reusable app" convention.

## Folder structure

```
app/
  core/            project-wide wiring: settings, DB engine/session, Redis client
  common/          shared SQLAlchemy Base + mixins (timestamps, UUID PKs) used by every app
  apps/
    users/         one Django-style "app" per domain area
      models.py    SQLAlchemy models
      schemas.py   Pydantic request/response schemas
      router.py    FastAPI APIRouter (the "views")
      services.py  business logic, kept out of route handlers
    organizations/
    memberships/   user <-> organization, carries the role (tenant membership + RBAC)
    projects/
    tasks/
    comments/
    audit/
  main.py          FastAPI app instance, includes every app's router
alembic/           migration environment; env.py imports every app's models.py
                   so autogenerate sees the full metadata
tests/             mirrors app/apps/ layout, httpx AsyncClient against the ASGI app
```

Adding a new domain app means adding a new `app/apps/<name>/` package with the
same four files and wiring its router into `app/main.py` — no other structural
changes required.

## Multi-tenancy model

Tenancy is row-level, not schema-per-tenant: every tenant-scoped table carries
an `organization_id` foreign key (directly, or transitively through a parent
that does). `organizations` is the tenant. `memberships` is the join table
between `users` and `organizations` and is where a user's **role** within a
given organization lives — a user can belong to multiple organizations with a
different role in each.

## Configuration

All runtime configuration is environment-variable driven (`app/core/config.py`,
a `pydantic-settings` `Settings` object), backed by a `.env` file consumed by
both the `api` container and directly by the `db`/`redis` containers in
`docker-compose.yml`. `.env.example` documents every variable; `.env` itself is
gitignored. Swapping to a different database (e.g. a managed cloud instance)
is a one-line change to `DATABASE_URL`.

## Running locally

```
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

Migrations:

```
docker compose exec api alembic revision --autogenerate -m "message"
docker compose exec api alembic upgrade head
```
