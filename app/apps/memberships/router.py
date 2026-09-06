import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.memberships import services
from app.apps.memberships.models import Membership, OrgRole
from app.apps.memberships.schemas import MembershipInvite, MembershipRead, MembershipRoleUpdate
from app.core.database import get_db
from app.core.permissions import get_current_membership, require_role

router = APIRouter(prefix="/memberships", tags=["memberships"])


def _to_read(membership: Membership) -> MembershipRead:
    return MembershipRead(
        id=membership.id,
        user_id=membership.user_id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.get("", response_model=list[MembershipRead])
async def list_members(
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[MembershipRead]:
    members = await services.list_memberships(db, membership.organization_id)
    return [_to_read(member) for member in members]


@router.post(
    "/invite",
    response_model=MembershipRead,
    status_code=201,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def invite_member(
    payload: MembershipInvite,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> MembershipRead:
    created = await services.invite_member(
        db, membership.organization_id, membership, payload.email, payload.role
    )
    return _to_read(created)


@router.patch(
    "/{membership_id}/role",
    response_model=MembershipRead,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def update_member_role(
    membership_id: uuid.UUID,
    payload: MembershipRoleUpdate,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> MembershipRead:
    updated = await services.update_member_role(
        db, membership.organization_id, membership_id, membership, payload.role
    )
    return _to_read(updated)


@router.delete(
    "/{membership_id}",
    status_code=204,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def remove_member(
    membership_id: uuid.UUID,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> None:
    await services.remove_member(db, membership.organization_id, membership_id, membership)
