import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.apps.memberships.models import Membership, OrgRole
from app.apps.organizations.models import Organization
from app.apps.users.models import User

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_INVALID_CHARS.sub("-", name.strip().lower()).strip("-")
    return slug or "org"


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while await db.scalar(select(Organization).where(Organization.slug == slug)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


async def create_organization(db: AsyncSession, owner: User, name: str) -> Organization:
    """Creates a new organization and makes the caller its owner. A user can
    own or belong to any number of organizations independently of their role
    in any other organization."""
    organization = Organization(name=name, slug=await _unique_slug(db, _slugify(name)))
    db.add(organization)
    await db.flush()

    db.add(Membership(user_id=owner.id, organization_id=organization.id, role=OrgRole.OWNER))
    await db.commit()
    await db.refresh(organization)
    return organization


async def list_user_organizations(db: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    """All organizations a user belongs to, owned or invited into alike."""
    result = await db.scalars(
        select(Membership)
        .where(Membership.user_id == user_id)
        .options(selectinload(Membership.organization))
    )
    return list(result)


async def get_organization(db: AsyncSession, organization_id: uuid.UUID) -> Organization:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return organization


async def update_organization(db: AsyncSession, organization_id: uuid.UUID, name: str) -> Organization:
    organization = await get_organization(db, organization_id)
    organization.name = name
    await db.commit()
    await db.refresh(organization)
    return organization


async def delete_organization(db: AsyncSession, organization_id: uuid.UUID) -> None:
    organization = await get_organization(db, organization_id)
    await db.delete(organization)
    await db.commit()
