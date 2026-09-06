import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.apps.memberships.models import OrgRole
from app.common.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Invitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A pending offer to join an organization, sent to an email address
    that may or may not have an account yet. Becomes a Membership only once
    accepted (see app/apps/invitations/services.py::accept_invitation)."""

    __tablename__ = "invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[OrgRole] = mapped_column(
        SqlEnum(OrgRole, native_enum=False, length=20, validate_strings=True)
    )
    status: Mapped[InvitationStatus] = mapped_column(
        SqlEnum(InvitationStatus, native_enum=False, length=20, validate_strings=True),
        default=InvitationStatus.PENDING,
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
