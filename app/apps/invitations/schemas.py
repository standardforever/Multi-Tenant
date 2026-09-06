import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.apps.invitations.models import InvitationStatus
from app.apps.memberships.models import OrgRole


class InvitationCreate(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER


class InvitationRoleUpdate(BaseModel):
    role: OrgRole


class InvitationAccept(BaseModel):
    token: str = Field(min_length=1)


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: OrgRole
    status: InvitationStatus
    token: str
    expires_at: datetime
    last_reminded_at: datetime | None
    created_at: datetime


class InvitationPublicRead(BaseModel):
    """What an unauthenticated invitee sees before logging in or signing
    up — deliberately excludes the token itself (the link already carries
    it) and anything internal."""

    organization_name: str
    email: EmailStr
    role: OrgRole
    status: InvitationStatus
    expires_at: datetime
