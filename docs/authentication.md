# Authentication & Permissions

## Overview

Two independent login paths issue the same kind of credential: a
**JWT access/refresh token pair**. Every protected endpoint depends on that
pair to identify `request.user`; a second, optional dependency layer gates
endpoints on organization membership + role.

```
password login  ─┐
                  ├──► access_token (15 min) + refresh_token (30 days)
google login    ──┘
```

## Endpoints (`app/apps/auth/router.py`)

| Method | Path                    | Purpose                                                |
|--------|-------------------------|---------------------------------------------------------|
| POST   | `/auth/register`        | Create a password-based account, returns a token pair   |
| POST   | `/auth/login`           | Verify email+password, returns a token pair             |
| POST   | `/auth/refresh`         | Exchange a refresh token for a new pair (rotates it)     |
| POST   | `/auth/logout`          | Revoke a refresh token                                  |
| GET    | `/auth/me`              | Return the current user (requires `Authorization` header)|
| GET    | `/auth/google/login`    | Redirect to Google's consent screen                      |
| GET    | `/auth/google/callback` | Google redirects here; exchanges code, issues our tokens |

## JWTs (`app/core/security.py`)

- Signed with `HS256` using `SECRET_KEY`.
- Access token: `type=access`, 15 minute expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- Refresh token: `type=refresh`, 30 day expiry (`REFRESH_TOKEN_EXPIRE_DAYS`).
- Both carry a `jti` (unique token id).

Every issued **refresh** token's `jti` is written to Redis
(`refresh_token:<jti>` -> `user_id`) with a TTL matching the token's expiry.
This is what makes a refresh token revocable — a JWT itself can't be
"un-issued", so we track liveness in Redis instead of trusting the token's
signature alone:

- `/auth/refresh` looks up the `jti` in Redis, **deletes it immediately**
  (single use), and issues a brand new pair. Reusing an old refresh token
  after it's been rotated returns `401` — this limits the damage if a
  refresh token is ever stolen, since a replay is instantly detectable
  (both the attacker's and the legitimate user's next refresh attempt fail).
- `/auth/logout` deletes the `jti` directly, revoking it immediately rather
  than waiting for it to expire.

Access tokens are *not* tracked in Redis — they're short-lived enough
(15 min) that revocation-on-demand isn't worth a Redis round trip on every
authenticated request. Logging out only guarantees the *refresh* token
stops working; any already-issued access token remains valid until it
naturally expires.

## Password auth

Passwords are hashed with `bcrypt` directly (`app/core/security.py`), no
ORM-level plaintext ever touches the database. `User.hashed_password` is
nullable — a user who only ever signed in via Google has no password and
cannot use `/auth/login`.

## Google OAuth (`app/apps/auth/services.py`)

Backend-driven Authorization Code flow — the API itself talks to Google,
the frontend never sees a Google token:

1. `GET /auth/google/login?next=<url>` — generates a random `state`, stores
   `state -> next` in Redis (`oauth_state:<state>`, 5 minute TTL,
   `OAUTH_STATE_TTL_SECONDS`), then 307-redirects the browser to Google's
   consent screen with that `state`.
2. Google redirects back to `GET /auth/google/callback?code=...&state=...`.
   The `state` is looked up in Redis (CSRF protection — proves the callback
   corresponds to a login we actually started) and deleted (single use).
3. The backend exchanges `code` for a Google access token
   (server-to-server POST to `oauth2.googleapis.com/token`), then calls
   Google's `userinfo` endpoint to get `{sub, email, email_verified, name}`.
4. `sub` (Google's stable per-user id) is matched against `OAuthAccount`.
   - Found → use its linked `User`.
   - Not found, but a `User` with that verified email exists → link a new
     `OAuthAccount` to that existing user (password and Google login now
     both work for the same account).
   - Neither found → create a new `User` (no password) + `OAuthAccount`.
5. Issue our own token pair exactly like a normal login, then redirect the
   browser to `next#access_token=...&refresh_token=...` (tokens in the URL
   **fragment**, not the query string, so they aren't sent to any server
   or logged by default).

Requires real credentials in `.env`: `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (must exactly match an
authorized redirect URI configured in the Google Cloud Console).

## Permissions / RBAC (`app/core/permissions.py`)

Multi-tenancy is row-level (see [architecture.md](architecture.md)); which
organization a request acts on is carried in the **`X-Org-Id`** header
(not the URL). Two dependencies build on `get_current_user`:

- **`get_current_membership`** — reads `X-Org-Id`, loads the caller's
  `Membership` row for that org. `403` if the user isn't a member of it.
- **`require_role(minimum: OrgRole)`** — a dependency *factory*. Roles rank
  `MEMBER < ADMIN < OWNER` (`ROLE_RANK` in `app/apps/memberships/models.py`);
  it checks the caller's role in the target org is at least `minimum`.

Any router gates itself with one line:

```python
router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_role(OrgRole.MEMBER))],
)
```

or per-route, when only some endpoints need a higher bar:

```python
@router.delete("/{project_id}", dependencies=[Depends(require_role(OrgRole.ADMIN))])
```

`require_superuser` is a separate, non-org-scoped dependency for
platform-level endpoints (e.g. future admin/audit tooling), gated on
`User.is_superuser` instead of a membership.

## Tests

- `tests/apps/auth/test_auth_flow.py` — integration test against the real
  Postgres + Redis containers: register → duplicate rejected → login →
  wrong password rejected → `/auth/me` → refresh rotation → reused old
  refresh token rejected → logout → refresh after logout rejected.
- `tests/test_permissions.py` — unit tests for `require_role`, overriding
  `get_current_membership` with a plain (unsaved) `Membership` to prove the
  role-rank comparison allows/blocks correctly, independent of the database.

Run with `docker compose exec api pytest -v`.

## What's intentionally not built yet

- Organization/membership CRUD (creating an org, inviting a member, changing
  a role) — needed before `require_role` can be exercised against real data,
  but out of scope for "authentication flow".
- Email verification for password signups.
- Access-token revocation (accepted tradeoff — see above).
