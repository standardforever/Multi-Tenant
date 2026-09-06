import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.invitations.models import Invitation, InvitationStatus
from app.apps.memberships.models import ROLE_RANK, Membership, OrgRole
from app.apps.organizations.models import Organization
from app.apps.users.models import User
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.email import send_email

settings = get_settings()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


async def _get_active_pending_invitation(
    db: AsyncSession, organization_id: uuid.UUID, email: str
) -> Invitation | None:
    return await db.scalar(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
            Invitation.email == email,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > datetime.now(timezone.utc),
        )
    )


async def create_invitation(
    db: AsyncSession,
    organization_id: uuid.UUID,
    inviter_membership: Membership,
    email: str,
    role: OrgRole,
) -> Invitation:
    if ROLE_RANK[role] > ROLE_RANK[inviter_membership.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot invite at a role higher than your own")

    already_member = await db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id, User.email == email)
    )
    if already_member is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already belongs to a member of this organization")

    if await _get_active_pending_invitation(db, organization_id, email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An active invitation is already pending for that email")

    invitation = Invitation(
        organization_id=organization_id,
        email=email,
        role=role,
        status=InvitationStatus.PENDING,
        token=_generate_token(),
        invited_by_user_id=inviter_membership.user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.invitation_expire_days),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def list_invitations(db: AsyncSession, organization_id: uuid.UUID) -> list[Invitation]:
    result = await db.scalars(
        select(Invitation)
        .where(Invitation.organization_id == organization_id)
        .order_by(Invitation.created_at.desc())
    )
    return list(result)


async def _get_org_invitation(
    db: AsyncSession, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> Invitation:
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.organization_id == organization_id
        )
    )
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    return invitation


async def update_invitation_role(
    db: AsyncSession,
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    actor_membership: Membership,
    new_role: OrgRole,
) -> Invitation:
    invitation = await _get_org_invitation(db, organization_id, invitation_id)
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a pending invitation's role can be changed")
    if ROLE_RANK[new_role] > ROLE_RANK[actor_membership.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot assign a role higher than your own")

    invitation.role = new_role
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def revoke_invitation(db: AsyncSession, organization_id: uuid.UUID, invitation_id: uuid.UUID) -> Invitation:
    invitation = await _get_org_invitation(db, organization_id, invitation_id)
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a pending invitation can be revoked")

    invitation.status = InvitationStatus.REVOKED
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def remind_invitation(db: AsyncSession, organization_id: uuid.UUID, invitation_id: uuid.UUID) -> Invitation:
    invitation = await _get_org_invitation(db, organization_id, invitation_id)
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a pending invitation can be reminded")
    if invitation.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation has expired; revoke it and send a new one")

    invitation.last_reminded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def get_public_invitation(db: AsyncSession, token: str) -> tuple[Invitation, Organization]:
    invitation = await db.scalar(select(Invitation).where(Invitation.token == token))
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    organization = await db.get(Organization, invitation.organization_id)
    return invitation, organization


async def accept_invitation(db: AsyncSession, token: str, current_user: User) -> Membership:
    invitation = await db.scalar(select(Invitation).where(Invitation.token == token))
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation is no longer valid")
    if invitation.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation has expired")
    if invitation.email.lower() != current_user.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This invitation was sent to a different email address")

    existing_membership = await db.scalar(
        select(Membership).where(
            Membership.organization_id == invitation.organization_id,
            Membership.user_id == current_user.id,
        )
    )
    if existing_membership is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already a member of this organization")

    membership = Membership(
        user_id=current_user.id, organization_id=invitation.organization_id, role=invitation.role
    )
    db.add(membership)
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(membership)
    return membership


def _invite_email_html(
    organization_name: str, inviter_name: str, role: OrgRole, accept_url: str, expires_at: datetime
) -> str:
    return (
        f"<p>{inviter_name} invited you to join <strong>{organization_name}</strong> "
        f"as <strong>{role.value}</strong>.</p>"
        f'<p><a href="{accept_url}">Accept invitation</a></p>'
        f"<p>This invitation expires on {expires_at:%Y-%m-%d %H:%M} UTC.</p>"
    )


async def send_invitation_email_background(invitation_id: uuid.UUID) -> None:
    """Runs as a FastAPI BackgroundTask, i.e. after the HTTP response has
    already been sent — the request's own DB session is closed by then, so
    this opens a fresh one rather than reusing anything request-scoped."""
    async with async_session_factory() as db:
        invitation = await db.get(Invitation, invitation_id)
        if invitation is None:
            return
        organization = await db.get(Organization, invitation.organization_id)
        inviter = await db.get(User, invitation.invited_by_user_id)

        accept_url = f"{settings.frontend_url}/invitations/{invitation.token}"
        await send_email(
            to=invitation.email,
            subject=f"You've been invited to join {organization.name}",
            html=_invite_email_html(
                organization.name,
                inviter.full_name or inviter.email,
                invitation.role,
                accept_url,
                invitation.expires_at,
            ),
        )
