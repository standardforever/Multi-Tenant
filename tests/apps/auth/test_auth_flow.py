import uuid

import pytest


@pytest.mark.asyncio
async def test_register_login_refresh_logout_flow(client):
    email = f"{uuid.uuid4().hex}@example.com"

    register_response = await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert register_response.status_code == 201
    tokens = register_response.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    duplicate_response = await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert duplicate_response.status_code == 409

    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    assert login_response.status_code == 200

    wrong_password_response = await client.post(
        "/auth/login", json={"email": email, "password": "wrong"}
    )
    assert wrong_password_response.status_code == 401

    me_response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email

    unauthenticated_response = await client.get("/auth/me")
    assert unauthenticated_response.status_code == 401

    refresh_response = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_response.status_code == 200
    rotated_tokens = refresh_response.json()

    # The old refresh token was single-use and is now revoked.
    reuse_response = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse_response.status_code == 401

    logout_response = await client.post(
        "/auth/logout", json={"refresh_token": rotated_tokens["refresh_token"]}
    )
    assert logout_response.status_code == 204

    refresh_after_logout_response = await client.post(
        "/auth/refresh", json={"refresh_token": rotated_tokens["refresh_token"]}
    )
    assert refresh_after_logout_response.status_code == 401
