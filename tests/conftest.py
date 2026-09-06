import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import engine
from app.core.redis import redis_client
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def sent_emails(monkeypatch):
    """Autouse: no test should ever hit the real Resend API. Stubs out the
    single call site (app.apps.invitations.services.send_email) with a
    recorder; tests that care about email content can depend on this
    fixture by name to inspect what would have been sent."""
    calls: list[dict] = []

    async def fake_send_email(to: str, subject: str, html: str) -> None:
        calls.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr("app.apps.invitations.services.send_email", fake_send_email)
    return calls


@pytest.fixture(autouse=True)
async def _reset_pooled_connections():
    """pytest-asyncio gives each test its own event loop, but the SQLAlchemy
    engine and Redis client are module-level singletons whose pools cache
    connections bound to whichever loop created them. Dispose both after
    every test so the next test's loop opens fresh ones instead of reusing
    now-invalid ones (avoids "attached to a different loop" errors)."""
    yield
    await engine.dispose()
    await redis_client.aclose()
