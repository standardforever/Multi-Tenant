# Organizations & Membership

## Model

- **Creating an organization makes the creator its owner.** There's no
  separate "become an owner" step — `POST /organizations` atomically creates
  the `Organization` row and an owning `Membership` row in one transaction
  (`app/apps/organizations/services.py::create_organization`).
- **A user can belong to any number of organizations independently.** Being a
  `member` (or even `admin`) of one organization has no bearing on their
  ability to create and own a completely separate one — every user is
  free to `POST /organizations` at any time, regardless of what they're
  already a member of elsewhere. `GET /organizations` returns the union:
  every org the caller owns *and* every org they've been invited into.
- Organizations don't nest and don't share data — each is an isolated tenant
  (see [architecture.md](architecture.md#multi-tenancy-model)). Which one a
  request acts on is the `X-Org-Id` header, per the project's tenant-scoping
  convention.

## Endpoints

### `app/apps/organizations/router.py`

| Method | Path                  | Auth                    | Purpose                                  |
|--------|-----------------------|--------------------------|-------------------------------------------|
| POST   | `/organizations`      | logged in                | Create an org; caller becomes its owner   |
| GET    | `/organizations`      | logged in                | List every org the caller belongs to      |
| GET    | `/organizations/current` | member (`X-Org-Id`)   | Details of the org in the header          |
| PATCH  | `/organizations/current` | owner (`X-Org-Id`)    | Rename the org                            |
| DELETE | `/organizations/current` | owner (`X-Org-Id`)    | Delete the org (cascades to memberships)  |

### `app/apps/memberships/router.py`

| Method | Path                          | Auth                  | Purpose                              |
|--------|-------------------------------|------------------------|----------------------------------------|
| GET    | `/memberships`                | member (`X-Org-Id`)    | List everyone in the current org        |
| POST   | `/memberships/invite`         | admin+ (`X-Org-Id`)    | Add an *existing* user by email + role  |
| PATCH  | `/memberships/{id}/role`      | admin+ (`X-Org-Id`)    | Change a member's role                  |
| DELETE | `/memberships/{id}`           | admin+ (`X-Org-Id`)    | Remove a member from the org            |

Slugs (`organizations.slug`) are auto-generated from the name
(`_slugify` + a `-2`, `-3`, ... suffix on collision) — not user-supplied, so
there's no separate validation surface for them yet.

## Invite guardrails

Inviting, promoting, or removing members through a shared RBAC surface
creates a few classic privilege-escalation and lockout footguns. All are
handled in `app/apps/memberships/services.py`, using the role ranking from
`app/apps/memberships/models.py::ROLE_RANK` (`member < admin < owner`):

- **Invite by email only** — `/memberships/invite` looks up an *existing*
  `User` by email. If nobody's registered with that email yet, it's a `404`
  telling the inviter to have them sign up first. There is no
  pending-invite-for-an-unregistered-email flow (that needs outbound email
  delivery — intentionally deferred, see below).
- **Can't invite/promote past your own rank** — an `admin` can invite or
  promote someone up to `admin`, never `owner`; only an `owner` can create
  another `owner`. (`ROLE_RANK[role] > ROLE_RANK[inviter.role]` → `403`.)
- **Can't touch someone ranked above you** — an `admin` can't demote or
  remove an `owner`. (`ROLE_RANK[actor.role] < ROLE_RANK[target.role]` →
  `403`.) Equal-rank peers *can* manage each other (two admins can remove
  one another) — deliberately permissive, since restricting that further
  wasn't asked for and isn't a real security boundary here (both already
  hold the same privileges).
- **An organization can never end up with zero owners** — demoting or
  removing the last remaining `owner` is a `400`
  (`_ensure_not_last_owner`). This is what stops an org from becoming
  unmanageable (nobody left with rename/delete/re-invite rights).
- **Duplicate invites rejected** — inviting someone already in the org is a
  `409`, not a silent no-op or a second membership row.

## What's intentionally not built yet

- **Pending invitations for unregistered emails.** Right now you can only
  invite someone who already has an account. A "real" invite system (invite
  token + email delivery + accept-on-signup) needs an email-sending
  integration, which hasn't been set up — noted here rather than half-built.
- **"Leave organization" self-service.** A member can be removed by an
  admin/owner via `DELETE /memberships/{id}`, but there's no dedicated
  self-service "leave" endpoint yet (would hit the same last-owner guard).
- **Organization-level settings/branding** — out of scope for this step.

## Tests

`tests/apps/organizations/test_organizations_flow.py` — one end-to-end
integration test against the real Postgres/Redis containers covering the
full story: create → owner in "my orgs" list → non-member blocked by
`X-Org-Id` → invite → invitee sees the org too → member blocked from
inviting → invitee creates *their own separate* org and now sees both with
the correct role in each → promote → self-escalation blocked → last-owner
demotion blocked → remove → removed user loses access but keeps their own
org → delete org → it disappears from the owner's list.

Run with `docker compose exec api pytest -v`.

### A note on the test suite itself

The SQLAlchemy engine and Redis client are module-level singletons
(`app/core/database.py`, `app/core/redis.py`), but `pytest-asyncio` gives
each test function its own event loop by default. Pooled connections opened
during one test are bound to that test's loop and become invalid once the
next test's loop starts, raising "attached to a different loop" errors.
`tests/conftest.py` fixes this with an autouse fixture that disposes the
engine's pool and closes the Redis client after every test, so the next
test's loop always opens fresh connections.
