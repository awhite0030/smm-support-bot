"""Basic tests for support-bot."""
import pytest
import asyncio
from app.health import check_database, check_redis, health_check
from app.db.tickets import get_pool


@pytest.mark.asyncio
async def test_database_connection():
    """Test PostgreSQL connection."""
    result = await check_database()
    assert result["status"] == "healthy"
    assert result["type"] == "postgres"


@pytest.mark.asyncio
async def test_database_query():
    """Test basic database query."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        assert result == 1


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint."""
    result = await health_check()
    assert "status" in result
    assert "checks" in result
    assert "database" in result["checks"]


def test_import_modules():
    """Test that all modules can be imported."""
    from app import config
    from app.db import tickets
    from app.bot.handlers.private import message
    from app.bot.handlers.group import command
    
    assert config is not None
    assert tickets is not None
    assert message is not None
    assert command is not None


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_database_connection())
    asyncio.run(test_database_query())
    asyncio.run(test_health_check())
    test_import_modules()
    print("✅ All tests passed")
