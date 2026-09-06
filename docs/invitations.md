# Invitations

Replaces the earlier shortcut (a `POST /memberships/invite` that only worked
for people who already had an account, and created a `Membership` instantly
with no acceptance step). Invitations are now a first-class, stateful object:
an admin sends one to an email address — registered or not — the invitee
gets a real email, and a `Membership` is only created once they accept.

## Model (`app/apps/invitations/models.py`)

```
Invitation
  organization_id   FK -> organizations.id, ON DELETE CASCADE
  email             the invited address (need not have an account yet)
  role              the OrgRole they'll be granted on acceptance
  status            pending | accepted | revoked
  token             random 32-byte urlsafe string, unique — the accept link
  invited_by_user_id FK -> users.id
  expires_at        default now() + INVITATION_EXPIRE_DAYS (7)
  accepted_at       set when accepted
  last_reminded_at  set each time a reminder is sent
```

No SQLAlchemy relationships are declared on `Invitation` — related
`Organization`/`User` rows are fetched with plain `db.get()` where needed
(mainly in the background email task, see below), which is simpler when the
model isn't traversed via ORM navigation anywhere else. Because of that,
cascade-on-delete is handled at the **database** level
(`ondelete="CASCADE"` on the FK), not via an ORM `cascade=` option — deleting
an organization deletes its invitations regardless of whether anything in
the current session has ever loaded them. (This was actually found by a
failing test: deleting an org with a pending invitation raised a
`ForeignKeyViolationError` until the FK got `ondelete="CASCADE"`.)

## Endpoints (`app/apps/invitations/router.py`)

| Method | Path                          | Auth                 | Purpose                                    |
|--------|-------------------------------|-----------------------|----------------------------------------------|
| POST   | `/invitations`                | admin+ (`X-Org-Id`)   | Invite an email at a role                     |
| GET    | `/invitations`                | admin+ (`X-Org-Id`)   | List every invitation for the org (any status)|
| PATCH  | `/invitations/{id}`           | admin+ (`X-Org-Id`)   | Change a *pending* invitation's role          |
| POST   | `/invitations/{id}/remind`    | admin+ (`X-Org-Id`)   | Re-send the invite email                      |
| DELETE | `/invitations/{id}`           | admin+ (`X-Org-Id`)   | Revoke a *pending* invitation                 |
| GET    | `/invitations/by-token/{token}` | none (public)       | Preview an invite before logging in/signing up|
| POST   | `/invitations/accept`         | any logged-in user    | Accept, creating the Membership               |

`by-token` and `accept` aren't `X-Org-Id`-scoped — which organization they
act on comes from the invitation/token itself, not the caller's header.

## The accept flow, end to end

1. Admin calls `POST /invitations` with `{email, role}`.
   `app/apps/invitations/services.py::create_invitation` checks the same
   escalation guard as memberships (can't invite above your own rank, see
   [organizations.md](organizations.md#invite-guardrails)), that the email
   isn't already a member, and that there's no other *active* pending
   invitation for that email (`409` on either) — then creates the row and
   returns `201` with the invitation, including its `token`.
2. The route schedules `send_invitation_email_background` as a
   **FastAPI `BackgroundTask`** — it runs after the HTTP response has
   already gone out, so creating the invitation is not slowed down by an
   external email API call. The invitee gets an email with an accept link:
   `{FRONTEND_URL}/invitations/{token}`.
3. Before logging in, the frontend can call
   `GET /invitations/by-token/{token}` to show "You've been invited to
   join **{org}**" — this is public precisely so it works pre-auth.
4. If the invitee has no account, they hit `POST /auth/register` with the
   *same* email. If they already have one, they just log in.
5. `POST /invitations/accept` with `{token}`, authenticated as that user.
   `accept_invitation` checks: invitation still `pending`, not expired, and
   — the one check that only makes sense at this final step —
   **the logged-in user's email matches the invitation's email**
   (case-insensitively). Only then is the `Membership` created and the
   invitation marked `accepted`.

## Why a background task, not a job queue

`send_invitation_email_background` runs via FastAPI's built-in
`BackgroundTasks`, not a queue (Celery/arq/etc). This is deliberate: a
single transactional email with no retry/scheduling requirement doesn't
need standing infrastructure, and it's what "activate the sending in the
background" means here — the request returns immediately, the email goes
out after. If invitations later need retries, delayed sends, or a
dead-letter queue, that's the point to introduce a real worker; nothing
here should be read as ruling that out later.

One consequence of using `BackgroundTasks` this way: it must **not** reuse
the request's own DB session — by the time a background task runs, that
session's dependency (`get_db`'s `yield`) has already been torn down.
`send_invitation_email_background` opens a fresh session via
`async_session_factory()` directly instead of taking `db` as a parameter.

## Reminders and revocation

- **Remind** (`POST /invitations/{id}/remind`) re-sends the same email and
  stamps `last_reminded_at`. Blocked (`400`) if the invitation isn't
  `pending`, or if it's already expired — an expired invite should be
  revoked and re-sent fresh, not nudged (reminding does **not** extend
  `expires_at`).
- **Revoke** (`DELETE /invitations/{id}`) sets `status=revoked` (a soft
  delete, so it stays visible in `GET /invitations` for audit purposes) and
  is only allowed while still `pending`. A revoked invitation's token can
  never be accepted afterward.

## Sending email (`app/core/email.py`)

A single `send_email(to, subject, html)` function, calling Resend's HTTP
API directly via `httpx` (no SDK — matches how Google OAuth is already
called in this codebase). Configured via env vars:

- `RESEND_API_KEY` — **never commit the real value.** `.env.example` ships
  this blank; the real key lives only in the local, gitignored `.env`.
- `EMAIL_FROM` — must be a sender identity verified in the Resend dashboard
  for the sending domain.
- If `RESEND_API_KEY` is unset, `send_email` logs a warning and no-ops
  (useful for local dev without setting up email at all).
- Any Resend/network failure is caught and logged, never raised — there's
  no request left by the time this runs to surface an error to.

## What's intentionally not built yet

- **Retry/backoff on email delivery failure.** A failed send is logged and
  otherwise silently dropped; the admin can always hit "remind" manually.
- **Auto-expiring the `status` column.** Expiry is checked at the moment of
  use (`accept`/`remind`) by comparing `expires_at` to now, not by a
  scheduled job that flips `pending` rows to some `expired` status — so
  `GET /invitations` can still show an old, technically-expired row as
  `pending` until someone tries to act on it. Fine for now; would need a
  cron/worker to change.
- **Rate-limiting reminders.** No cooldown between reminder sends.

## Tests

`tests/apps/invitations/test_invitations_flow.py` covers: inviting an email
with **no existing account**, then registering and accepting (the core new
capability); duplicate/escalation/wrong-email/expired guards; revoke
blocking further reminders and acceptance; remind sending a second email.

All tests use an autouse fixture in `tests/conftest.py`
(`sent_emails`) that monkeypatches `app.apps.invitations.services.send_email`
so the suite **never** calls the real Resend API — tests that care about
email content take `sent_emails` as a parameter to inspect what was
"sent". The real integration (this exact key + sender domain) was verified
manually once, outside the test suite, by sending a live email.
