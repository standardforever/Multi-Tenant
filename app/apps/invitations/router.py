import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.invitations import services
from app.apps.invitations.schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationPublicRead,
    InvitationRead,
    InvitationRoleUpdate,
)
from app.apps.memberships.models import Membership, OrgRole
from app.apps.memberships.schemas import MembershipRead
from app.apps.users.models import User
from app.core.database import get_db
from app.core.permissions import get_current_membership, require_role
from app.core.security import get_current_user

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post(
    "",
    response_model=InvitationRead,
    status_code=201,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def create_invitation(
    payload: InvitationCreate,
    background_tasks: BackgroundTasks,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> InvitationRead:
    invitation = await services.create_invitation(
        db, membership.organization_id, membership, payload.email, payload.role
    )
    background_tasks.add_task(services.send_invitation_email_background, invitation.id)
    return InvitationRead.model_validate(invitation)


@router.get(
    "",
    response_model=list[InvitationRead],
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def list_invitations(
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[InvitationRead]:
    invitations = await services.list_invitations(db, membership.organization_id)
    return [InvitationRead.model_validate(invitation) for invitation in invitations]


@router.post(
    "/{invitation_id}/remind",
    response_model=InvitationRead,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def remind_invitation(
    invitation_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> InvitationRead:
    invitation = await services.remind_invitation(db, membership.organization_id, invitation_id)
    background_tasks.add_task(services.send_invitation_email_background, invitation.id)
    return InvitationRead.model_validate(invitation)


@router.patch(
    "/{invitation_id}",
    response_model=InvitationRead,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def update_invitation_role(
    invitation_id: uuid.UUID,
    payload: InvitationRoleUpdate,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> InvitationRead:
    invitation = await services.update_invitation_role(
        db, membership.organization_id, invitation_id, membership, payload.role
    )
    return InvitationRead.model_validate(invitation)


@router.delete(
    "/{invitation_id}",
    status_code=204,
    dependencies=[Depends(require_role(OrgRole.ADMIN))],
)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    membership: Membership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> None:
    await services.revoke_invitation(db, membership.organization_id, invitation_id)


@router.get("/by-token/{token}", response_model=InvitationPublicRead)
async def get_invitation_by_token(token: str, db: AsyncSession = Depends(get_db)) -> InvitationPublicRead:
    invitation, organization = await services.get_public_invitation(db, token)
    return InvitationPublicRead(
        organization_name=organization.name,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
    )


@router.post("/accept", response_model=MembershipRead)
async def accept_invitation(
    payload: InvitationAccept,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MembershipRead:
    membership = await services.accept_invitation(db, payload.token, current_user)
    return MembershipRead(
        id=membership.id,
        user_id=membership.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )
