import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.apps.memberships.models import Membership, OrgRole
from app.core.permissions import get_current_membership, require_role


def _build_app(membership: Membership) -> FastAPI:
    app = FastAPI()
    router = APIRouter()

    @router.get("/owner-only", dependencies=[Depends(require_role(OrgRole.OWNER))])
    async def owner_only():
        return {"ok": True}

    app.include_router(router)
    app.dependency_overrides[get_current_membership] = lambda: membership
    return app


@pytest.mark.asyncio
async def test_require_role_allows_sufficient_role():
    app = _build_app(Membership(role=OrgRole.OWNER))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/owner-only")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_require_role_blocks_insufficient_role():
    app = _build_app(Membership(role=OrgRole.MEMBER))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/owner-only")
    assert response.status_code == 403
