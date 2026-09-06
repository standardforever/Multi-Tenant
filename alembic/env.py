import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.common.models import Base
from app.core.config import get_settings

# Import each app's models so they register on Base.metadata before autogenerate runs.
from app.apps.audit import models as audit_models  # noqa: F401
from app.apps.comments import models as comments_models  # noqa: F401
from app.apps.memberships import models as memberships_models  # noqa: F401
from app.apps.organizations import models as organizations_models  # noqa: F401
from app.apps.projects import models as projects_models  # noqa: F401
from app.apps.tasks import models as tasks_models  # noqa: F401
from app.apps.users import models as users_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable: AsyncEngine = create_async_engine(config.get_main_option("sqlalchemy.url"))

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
