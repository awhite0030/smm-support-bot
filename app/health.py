"""Health check endpoint for monitoring."""
import asyncio
from typing import Dict, Any
from app.db.tickets import get_pool
from app.bot.utils.redis.redis import RedisStorage


async def check_database() -> Dict[str, Any]:
    """Check PostgreSQL connection."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "type": "postgres"}
    except Exception as e:
        return {"status": "unhealthy", "type": "postgres", "error": str(e)}


async def check_redis(redis: RedisStorage) -> Dict[str, Any]:
    """Check Redis connection."""
    try:
        await redis.redis.ping()
        return {"status": "healthy", "type": "redis"}
    except Exception as e:
        return {"status": "unhealthy", "type": "redis", "error": str(e)}


async def health_check(redis: RedisStorage = None) -> Dict[str, Any]:
    """Complete health check."""
    db_health = await check_database()
    redis_health = await check_redis(redis) if redis else {"status": "unknown", "type": "redis"}
    
    overall_status = "healthy" if all(
        h["status"] == "healthy" for h in [db_health, redis_health]
    ) else "unhealthy"
    
    return {
        "status": overall_status,
        "checks": {
            "database": db_health,
            "redis": redis_health,
        }
    }
