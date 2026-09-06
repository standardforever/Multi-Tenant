import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.apps.memberships.models import OrgRole


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class MyOrganization(BaseModel):
    """One row of "organizations I belong to" — owned or invited into."""

    id: uuid.UUID
    name: str
    slug: str
    my_role: OrgRole
