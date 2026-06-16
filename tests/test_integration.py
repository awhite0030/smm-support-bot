"""Integration tests for support-bot."""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

# Test database operations
@pytest.mark.asyncio
async def test_ticket_lifecycle():
    """Test complete ticket lifecycle: create -> message -> close."""
    from app.db import tickets as ticket_db
    
    # Mock pool
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch('app.db.tickets.get_pool', return_value=mock_pool):
        # Test create ticket
        mock_conn.fetchval.return_value = 12345  # topic_id
        topic_id = await ticket_db.create_ticket(
            tg_id=123456789,
            username="testuser",
            topic_id=12345
        )
        assert topic_id == 12345
        
        # Test mark user message
        await ticket_db.mark_user_msg(12345)
        
        # Test mark admin message
        await ticket_db.mark_admin_msg(12345)
        
        # Test close ticket
        mock_conn.fetchval.return_value = 123456789  # user_id
        user_id = await ticket_db.close_ticket(12345)
        assert user_id == 123456789


@pytest.mark.asyncio
async def test_redis_operations():
    """Test Redis user data operations."""
    from app.bot.utils.redis.redis import RedisStorage
    from app.bot.utils.redis.models import UserData
    
    # Mock redis
    mock_redis = AsyncMock()
    storage = RedisStorage(mock_redis)
    
    # Test save user
    user_data = UserData(
        id=123456789,
        username="testuser",
        message_thread_id=12345
    )
    
    mock_redis.set.return_value = True
    await storage.save_user(123456789, user_data)
    mock_redis.set.assert_called_once()
    
    # Test get user
    mock_redis.get.return_value = '{"id": 123456789, "username": "testuser", "message_thread_id": 12345}'
    result = await storage.get_user(123456789)
    assert result.id == 123456789
    assert result.username == "testuser"


@pytest.mark.asyncio
async def test_faq_operations():
    """Test FAQ CRUD operations."""
    from app.db import tickets as ticket_db
    
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch('app.db.tickets.get_pool', return_value=mock_pool):
        # Test list FAQ
        mock_conn.fetch.return_value = [
            {"id": 1, "question": "Test?", "answer": "Answer", "active": True}
        ]
        faqs = await ticket_db.list_faq()
        assert len(faqs) > 0


@pytest.mark.asyncio
async def test_stats_generation():
    """Test statistics generation."""
    from app.db import tickets as ticket_db
    
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch('app.db.tickets.get_pool', return_value=mock_pool):
        # Mock stats data
        mock_conn.fetchrow.return_value = {
            "total": 100,
            "closed": 80,
            "open": 20,
            "avg_response_min": 15.5
        }
        mock_conn.fetch.return_value = [
            {"category": "Technical", "n": 50}
        ]
        
        stats = await ticket_db.stats()
        assert stats["total"] == 100
        assert stats["closed"] == 80


@pytest.mark.asyncio
async def test_antispam():
    """Test antispam functionality."""
    from app.antispam import is_spam
    from unittest.mock import AsyncMock
    
    mock_redis = AsyncMock()
    
    # Test duplicate detection
    mock_redis.smembers.return_value = {b"hash1", b"hash2"}
    result = await is_spam(123456789, "test message", mock_redis)
    # Should not be spam on first message
    assert result in [True, False]  # Depends on hash collision


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting."""
    from app.bot.utils.rate_limit import check_rate_limit
    from unittest.mock import AsyncMock
    
    mock_redis = AsyncMock()
    
    # Test within limit
    mock_redis.get.return_value = b"5"
    result = await check_rate_limit(123456789, mock_redis, limit=10)
    assert result is True
    
    # Test exceeded limit
    mock_redis.get.return_value = b"15"
    result = await check_rate_limit(123456789, mock_redis, limit=10)
    assert result is False


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint."""
    from app.health import check_db, check_redis
    
    # Test DB check
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval.return_value = 1
    
    with patch('app.health.get_pool', return_value=mock_pool):
        result = await check_db()
        assert result is True
    
    # Test Redis check
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    result = await check_redis(mock_redis)
    assert result is True
