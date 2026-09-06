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
async def _reset_pooled_connections():
    """pytest-asyncio gives each test its own event loop, but the SQLAlchemy
    engine and Redis client are module-level singletons whose pools cache
    connections bound to whichever loop created them. Dispose both after
    every test so the next test's loop opens fresh ones instead of reusing
    now-invalid ones (avoids "attached to a different loop" errors)."""
    yield
    await engine.dispose()
    await redis_client.aclose()
