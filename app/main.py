from fastapi import FastAPI

import app.core.model_registry  # noqa: F401  (registers every app's models on Base.metadata)
from app.apps.audit.router import router as audit_router
from app.apps.auth.router import router as auth_router
from app.apps.comments.router import router as comments_router
from app.apps.memberships.router import router as memberships_router
from app.apps.organizations.router import router as organizations_router
from app.apps.projects.router import router as projects_router
from app.apps.tasks.router import router as tasks_router
from app.apps.users.router import router as users_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Multi-Tenant", debug=settings.debug)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(organizations_router)
app.include_router(memberships_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(comments_router)
app.include_router(audit_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
