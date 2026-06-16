"""Security middleware: rate limiting, PII masking"""
import re
import time
from typing import Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging

# Redis для rate limiting (импортируется из main)
_redis_client = None

def init_security(redis):
    global _redis_client
    _redis_client = redis

# Rate limiting: 100 req/min per IP
async def check_rate_limit(ip: str) -> bool:
    if not _redis_client:
        return True
    key = f"api_rl:{ip}"
    count = await _redis_client.incr(key)
    if count == 1:
        await _redis_client.expire(key, 60)
    return count <= 100

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Rate limit
        ip = request.client.host
        if not await check_rate_limit(ip):
            raise HTTPException(429, "Too many requests")
        
        response = await call_next(request)
        return response

# PII masking для логов
def mask_pii(text: str) -> str:
    """Маскирует tg_id, телефоны, email в логах"""
    # tg_id (обычно 9-10 цифр)
    text = re.sub(r'\b\d{9,10}\b', '***TG_ID***', text)
    # Телефоны
    text = re.sub(r'\+?\d[\d\s\-\(\)]{8,}', '***PHONE***', text)
    # Email
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***EMAIL***', text)
    return text

class PII_Filter(logging.Filter):
    def filter(self, record):
        record.msg = mask_pii(str(record.msg))
        if record.args:
            record.args = tuple(mask_pii(str(a)) if isinstance(a, str) else a for a in record.args)
        return True
