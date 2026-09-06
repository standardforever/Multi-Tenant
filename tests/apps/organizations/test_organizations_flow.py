import uuid

import pytest


async def _register(client, name: str) -> dict:
    email = f"{name}-{uuid.uuid4().hex}@example.com"
    response = await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery", "full_name": name}
    )
    assert response.status_code == 201
    tokens = response.json()
    return {"email": email, "access_token": tokens["access_token"]}


def _auth(user: dict) -> dict:
    return {"Authorization": f"Bearer {user['access_token']}"}


def _org(user: dict, org_id: str) -> dict:
    return {**_auth(user), "X-Org-Id": org_id}


@pytest.mark.asyncio
async def test_org_creation_invite_and_multi_org_membership(client):
    owner = await _register(client, "owner")
    invitee = await _register(client, "invitee")

    # Creating an organization makes the caller its owner.
    create_response = await client.post(
        "/organizations", headers=_auth(owner), json={"name": "Acme Inc"}
    )
    assert create_response.status_code == 201
    org = create_response.json()

    my_orgs = (await client.get("/organizations", headers=_auth(owner))).json()
    assert my_orgs == [{"id": org["id"], "name": "Acme Inc", "slug": org["slug"], "my_role": "owner"}]

    # A non-member is refused when scoping requests to this org.
    forbidden_response = await client.get("/organizations/current", headers=_org(invitee, org["id"]))
    assert forbidden_response.status_code == 403

    # Owner invites the second user as a plain member; invitee accepts.
    invite_response = await client.post(
        "/invitations",
        headers=_org(owner, org["id"]),
        json={"email": invitee["email"], "role": "member"},
    )
    assert invite_response.status_code == 201
    invitation_token = invite_response.json()["token"]

    duplicate_invite_response = await client.post(
        "/invitations",
        headers=_org(owner, org["id"]),
        json={"email": invitee["email"], "role": "member"},
    )
    assert duplicate_invite_response.status_code == 409

    accept_response = await client.post(
        "/invitations/accept", headers=_auth(invitee), json={"token": invitation_token}
    )
    assert accept_response.status_code == 200
    invitee_membership_id = accept_response.json()["id"]

    # The invited user now sees the organization in their own list.
    invitee_orgs = (await client.get("/organizations", headers=_auth(invitee))).json()
    assert invitee_orgs == [{"id": org["id"], "name": "Acme Inc", "slug": org["slug"], "my_role": "member"}]

    # A plain member cannot invite others.
    member_invite_response = await client.post(
        "/invitations",
        headers=_org(invitee, org["id"]),
        json={"email": owner["email"], "role": "member"},
    )
    assert member_invite_response.status_code == 403

    # An invited member can still create and own their own, separate organization.
    own_org_response = await client.post(
        "/organizations", headers=_auth(invitee), json={"name": "Invitee Co"}
    )
    assert own_org_response.status_code == 201
    own_org = own_org_response.json()

    invitee_orgs_after = (await client.get("/organizations", headers=_auth(invitee))).json()
    roles_by_org = {row["id"]: row["my_role"] for row in invitee_orgs_after}
    assert roles_by_org == {org["id"]: "member", own_org["id"]: "owner"}

    # Owner promotes the member to admin.
    promote_response = await client.patch(
        f"/memberships/{invitee_membership_id}/role",
        headers=_org(owner, org["id"]),
        json={"role": "admin"},
    )
    assert promote_response.status_code == 200
    assert promote_response.json()["role"] == "admin"

    # An admin cannot escalate themself (or anyone) to a role >= their own.
    self_escalate_response = await client.patch(
        f"/memberships/{invitee_membership_id}/role",
        headers=_org(invitee, org["id"]),
        json={"role": "owner"},
    )
    assert self_escalate_response.status_code == 403

    # The sole remaining owner cannot demote themself.
    owner_membership_id = next(
        row["id"]
        for row in (await client.get("/memberships", headers=_org(owner, org["id"]))).json()
        if row["email"] == owner["email"]
    )
    last_owner_response = await client.patch(
        f"/memberships/{owner_membership_id}/role",
        headers=_org(owner, org["id"]),
        json={"role": "admin"},
    )
    assert last_owner_response.status_code == 400

    # Owner removes the admin; they keep their own separate org.
    remove_response = await client.delete(
        f"/memberships/{invitee_membership_id}", headers=_org(owner, org["id"])
    )
    assert remove_response.status_code == 204

    removed_access_response = await client.get("/organizations/current", headers=_org(invitee, org["id"]))
    assert removed_access_response.status_code == 403

    invitee_orgs_final = (await client.get("/organizations", headers=_auth(invitee))).json()
    assert invitee_orgs_final == [{"id": own_org["id"], "name": "Invitee Co", "slug": own_org["slug"], "my_role": "owner"}]

    # Owner deletes the organization; it disappears from their own list too.
    delete_response = await client.delete("/organizations/current", headers=_org(owner, org["id"]))
    assert delete_response.status_code == 204

    owner_orgs_final = (await client.get("/organizations", headers=_auth(owner))).json()
    assert owner_orgs_final == []
