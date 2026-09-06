import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.apps.memberships.models import OrgRole


class MembershipRoleUpdate(BaseModel):
    role: OrgRole


class MembershipRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: OrgRole
    created_at: datetime
