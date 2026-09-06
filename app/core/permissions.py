import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.memberships.models import ROLE_RANK, Membership, OrgRole
from app.apps.users.models import User
from app.core.database import get_db
from app.core.security import get_current_user


async def get_current_membership(
    x_org_id: uuid.UUID = Header(..., alias="X-Org-Id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.organization_id == x_org_id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organization")
    return membership


def require_role(minimum: OrgRole) -> Callable[..., Coroutine[Any, Any, Membership]]:
    """Dependency factory: gates a route on the caller having at least
    `minimum` role in the organization given by the X-Org-Id header.

    Usage: dependencies=[Depends(require_role(OrgRole.ADMIN))]
    """

    async def dependency(membership: Membership = Depends(get_current_membership)) -> Membership:
        if ROLE_RANK[membership.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this organization")
        return membership

    return dependency


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Superuser privileges required")
    return current_user
