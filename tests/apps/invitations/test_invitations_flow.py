import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.apps.invitations.models import Invitation
from app.core.database import async_session_factory


async def _register(client, name: str) -> dict:
    email = f"{name}-{uuid.uuid4().hex}@example.com"
    response = await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery", "full_name": name}
    )
    assert response.status_code == 201
    return {"email": email, "access_token": response.json()["access_token"]}


def _auth(user: dict) -> dict:
    return {"Authorization": f"Bearer {user['access_token']}"}


def _org(user: dict, org_id: str) -> dict:
    return {**_auth(user), "X-Org-Id": org_id}


async def _create_org(client, owner: dict, name: str) -> dict:
    response = await client.post("/organizations", headers=_auth(owner), json={"name": name})
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_invite_unregistered_email_then_register_and_accept(client, sent_emails):
    owner = await _register(client, "owner")
    org = await _create_org(client, owner, "Acme Inc")

    invitee_email = f"newcomer-{uuid.uuid4().hex}@example.com"
    invite_response = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": invitee_email, "role": "member"}
    )
    assert invite_response.status_code == 201
    invitation = invite_response.json()
    assert invitation["status"] == "pending"

    # The email was "sent" (captured by the test stub) with a working accept link.
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == invitee_email
    assert invitation["token"] in sent_emails[0]["html"]

    # An unauthenticated visitor can look the invitation up by token before signing up.
    public_response = await client.get(f"/invitations/by-token/{invitation['token']}")
    assert public_response.status_code == 200
    assert public_response.json() == {
        "organization_name": "Acme Inc",
        "email": invitee_email,
        "role": "member",
        "status": "pending",
        "expires_at": invitation["expires_at"],
    }

    # The invitee didn't have an account — they register with the invited email, then accept.
    register_response = await client.post(
        "/auth/register", json={"email": invitee_email, "password": "correct-horse-battery"}
    )
    assert register_response.status_code == 201
    invitee_token = register_response.json()["access_token"]

    accept_response = await client.post(
        "/invitations/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
        json={"token": invitation["token"]},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["role"] == "member"

    my_orgs = (
        await client.get("/organizations", headers={"Authorization": f"Bearer {invitee_token}"})
    ).json()
    assert my_orgs == [{"id": org["id"], "name": "Acme Inc", "slug": org["slug"], "my_role": "member"}]

    # The token is single-use.
    reuse_response = await client.post(
        "/invitations/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
        json={"token": invitation["token"]},
    )
    assert reuse_response.status_code == 400


@pytest.mark.asyncio
async def test_escalation_guard_on_invite(client):
    owner = await _register(client, "owner")
    admin = await _register(client, "admin")
    org = await _create_org(client, owner, "Acme Inc")

    admin_invite = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": admin["email"], "role": "admin"}
    )
    admin_invitation = admin_invite.json()
    await client.post(
        "/invitations/accept", headers=_auth(admin), json={"token": admin_invitation["token"]}
    )

    escalate_response = await client.post(
        "/invitations", headers=_org(admin, org["id"]), json={"email": "someone@example.com", "role": "owner"}
    )
    assert escalate_response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_blocks_acceptance(client):
    owner = await _register(client, "owner")
    invitee = await _register(client, "invitee")
    org = await _create_org(client, owner, "Acme Inc")

    invite_response = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": invitee["email"], "role": "member"}
    )
    invitation_id = invite_response.json()["id"]
    token = invite_response.json()["token"]

    revoke_response = await client.delete(f"/invitations/{invitation_id}", headers=_org(owner, org["id"]))
    assert revoke_response.status_code == 204

    # Revoking again, or reminding a revoked invitation, is rejected.
    second_revoke_response = await client.delete(
        f"/invitations/{invitation_id}", headers=_org(owner, org["id"])
    )
    assert second_revoke_response.status_code == 400

    remind_response = await client.post(
        f"/invitations/{invitation_id}/remind", headers=_org(owner, org["id"])
    )
    assert remind_response.status_code == 400

    accept_response = await client.post("/invitations/accept", headers=_auth(invitee), json={"token": token})
    assert accept_response.status_code == 400

    # A fresh invitation can be sent for the same email once the old one is revoked.
    new_invite_response = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": invitee["email"], "role": "member"}
    )
    assert new_invite_response.status_code == 201


@pytest.mark.asyncio
async def test_wrong_email_cannot_accept(client):
    owner = await _register(client, "owner")
    invitee = await _register(client, "invitee")
    someone_else = await _register(client, "someone-else")
    org = await _create_org(client, owner, "Acme Inc")

    invite_response = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": invitee["email"], "role": "member"}
    )
    token = invite_response.json()["token"]

    wrong_user_response = await client.post(
        "/invitations/accept", headers=_auth(someone_else), json={"token": token}
    )
    assert wrong_user_response.status_code == 403


@pytest.mark.asyncio
async def test_remind_sends_another_email_and_sets_last_reminded_at(client, sent_emails):
    owner = await _register(client, "owner")
    invitee = await _register(client, "invitee")
    org = await _create_org(client, owner, "Acme Inc")

    invite_response = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": invitee["email"], "role": "member"}
    )
    invitation_id = invite_response.json()["id"]
    assert len(sent_emails) == 1

    remind_response = await client.post(
        f"/invitations/{invitation_id}/remind", headers=_org(owner, org["id"])
    )
    assert remind_response.status_code == 200
    assert remind_response.json()["last_reminded_at"] is not None
    assert len(sent_emails) == 2


@pytest.mark.asyncio
async def test_expired_invitation_cannot_be_accepted_or_reminded(client):
    owner = await _register(client, "owner")
    invitee = await _register(client, "invitee")
    org = await _create_org(client, owner, "Acme Inc")

    invite_response = await client.post(
        "/invitations", headers=_org(owner, org["id"]), json={"email": invitee["email"], "role": "member"}
    )
    invitation_id = invite_response.json()["id"]
    token = invite_response.json()["token"]

    async with async_session_factory() as db:
        invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invitation_id)))
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db.commit()

    accept_response = await client.post("/invitations/accept", headers=_auth(invitee), json={"token": token})
    assert accept_response.status_code == 400

    remind_response = await client.post(
        f"/invitations/{invitation_id}/remind", headers=_org(owner, org["id"])
    )
    assert remind_response.status_code == 400
