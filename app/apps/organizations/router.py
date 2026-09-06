from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.memberships.models import Membership, OrgRole
from app.apps.organizations import services
from app.apps.organizations.schemas import (
    MyOrganization,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.apps.users.models import User
from app.core.database import get_db
from app.core.permissions import get_current_membership, require_role
from app.core.security import get_current_user

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    organization = await services.create_organization(db, current_user, payload.name)
    return OrganizationRead.model_validate(organization)


@router.get("", response_model=list[MyOrganization])
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MyOrganization]:
    memberships = await services.list_user_organizations(db, current_user.id)
    return [
        MyOrganization(
            id=membership.organization.id,
            name=membership.organization.name,
            slug=membership.organization.slug,
            my_role=membership.role,
        )
        for membership in memberships
    ]


@router.get("/current", response_model=OrganizationRead)
async def get_current_organization(
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    organization = await services.get_organization(db, membership.organization_id)
    return OrganizationRead.model_validate(organization)


@router.patch(
    "/current",
    response_model=OrganizationRead,
    dependencies=[Depends(require_role(OrgRole.OWNER))],
)
async def update_current_organization(
    payload: OrganizationUpdate,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    organization = await services.update_organization(db, membership.organization_id, payload.name)
    return OrganizationRead.model_validate(organization)


@router.delete(
    "/current",
    status_code=204,
    dependencies=[Depends(require_role(OrgRole.OWNER))],
)
async def delete_current_organization(
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> None:
    await services.delete_organization(db, membership.organization_id)
