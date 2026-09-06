import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.apps.memberships.models import ROLE_RANK, Membership, OrgRole
from app.apps.users.models import User


async def _get_membership_with_user(db: AsyncSession, membership_id: uuid.UUID) -> Membership | None:
    return await db.scalar(
        select(Membership).where(Membership.id == membership_id).options(selectinload(Membership.user))
    )


async def _get_org_membership(
    db: AsyncSession, organization_id: uuid.UUID, membership_id: uuid.UUID
) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.id == membership_id, Membership.organization_id == organization_id
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    return membership


async def _ensure_not_last_owner(
    db: AsyncSession, organization_id: uuid.UUID, excluding_membership_id: uuid.UUID
) -> None:
    remaining_owners = await db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == OrgRole.OWNER,
            Membership.id != excluding_membership_id,
        )
    )
    if remaining_owners == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Organization must have at least one owner")


async def list_memberships(db: AsyncSession, organization_id: uuid.UUID) -> list[Membership]:
    result = await db.scalars(
        select(Membership)
        .where(Membership.organization_id == organization_id)
        .options(selectinload(Membership.user))
    )
    return list(result)


async def invite_member(
    db: AsyncSession,
    organization_id: uuid.UUID,
    inviter: Membership,
    email: str,
    role: OrgRole,
) -> Membership:
    if ROLE_RANK[role] > ROLE_RANK[inviter.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot grant a role higher than your own")

    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No account exists for that email yet — they need to register before being invited",
        )

    existing = await db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id, Membership.user_id == user.id
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member of this organization")

    membership = Membership(user_id=user.id, organization_id=organization_id, role=role)
    db.add(membership)
    await db.commit()
    return await _get_membership_with_user(db, membership.id)


async def update_member_role(
    db: AsyncSession,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    actor: Membership,
    new_role: OrgRole,
) -> Membership:
    target = await _get_org_membership(db, organization_id, membership_id)

    if ROLE_RANK[actor.role] < ROLE_RANK[target.role] or ROLE_RANK[actor.role] < ROLE_RANK[new_role]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Cannot assign a role equal to or higher than your own"
        )

    if target.role == OrgRole.OWNER and new_role != OrgRole.OWNER:
        await _ensure_not_last_owner(db, organization_id, target.id)

    target.role = new_role
    await db.commit()
    return await _get_membership_with_user(db, target.id)


async def remove_member(
    db: AsyncSession, organization_id: uuid.UUID, membership_id: uuid.UUID, actor: Membership
) -> None:
    target = await _get_org_membership(db, organization_id, membership_id)

    if ROLE_RANK[actor.role] < ROLE_RANK[target.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot remove a member with a higher role than your own")

    if target.role == OrgRole.OWNER:
        await _ensure_not_last_owner(db, organization_id, target.id)

    await db.delete(target)
    await db.commit()
