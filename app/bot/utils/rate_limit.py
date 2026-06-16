"""Rate limiting via shared Redis pool with in-memory fallback."""
import time
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Shared Redis client (injected from main)
_redis = None
# In-memory fallback when Redis is down
_memory_store: Dict[int, list[float]] = {}
_WINDOW = 60
_MAX_MSGS = 10


def init_rate_limiter(redis_client) -> None:
    """Set the shared Redis client for rate limiting."""
    global _redis
    _redis = redis_client


def _cleanup_memory(tg_id: int) -> None:
    """Remove expired entries from in-memory store."""
    if tg_id in _memory_store:
        cutoff = time.time() - _WINDOW
        _memory_store[tg_id] = [t for t in _memory_store[tg_id] if t > cutoff]
        if not _memory_store[tg_id]:
            del _memory_store[tg_id]


async def check_rate_limit(tg_id: int, max_msgs: int = _MAX_MSGS, window_sec: int = _WINDOW) -> bool:
    """
    Returns True if user is within rate limit, False if exceeded.
    Uses shared Redis pool; falls back to in-memory if Redis is unavailable.
    """
    global _redis

    if _redis is not None:
        try:
            key = f"rate:{tg_id}"
            count = await _redis.incr(key)
            if count == 1:
                await _redis.expire(key, window_sec)
            return count <= max_msgs
        except Exception:
            logger.warning("Rate limiter Redis failed, falling back to in-memory")

    # In-memory fallback
    now = time.time()
    if tg_id not in _memory_store:
        _memory_store[tg_id] = []
    _memory_store[tg_id].append(now)
    _cleanup_memory(tg_id)
    return len(_memory_store.get(tg_id, [])) <= max_msgs
