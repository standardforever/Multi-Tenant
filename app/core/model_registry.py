"""Imports every app's models module so SQLAlchemy can resolve cross-app
relationship() string references before any query runs. Import this before
the app starts serving requests (see app/main.py). Mirrors the same import
list in alembic/env.py, which needs it for autogenerate."""

from app.apps.audit import models as audit_models  # noqa: F401
from app.apps.comments import models as comments_models  # noqa: F401
from app.apps.memberships import models as memberships_models  # noqa: F401
from app.apps.organizations import models as organizations_models  # noqa: F401
from app.apps.projects import models as projects_models  # noqa: F401
from app.apps.tasks import models as tasks_models  # noqa: F401
from app.apps.users import models as users_models  # noqa: F401
