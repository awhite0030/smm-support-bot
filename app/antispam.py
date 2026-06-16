"""Advanced anti-spam: strikes, duplicate detection, captcha"""
import hashlib
from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import random

# Redis для хранения состояния
_redis = None

def init_antispam(redis):
    global _redis
    _redis = redis

# Детекция дубликатов
async def is_duplicate_message(tg_id: int, text: str) -> bool:
    """Проверяет последние 3 сообщения на дубли"""
    if not _redis or not text:
        return False
    
    msg_hash = hashlib.md5(text.encode()).hexdigest()
    key = f"msg_history:{tg_id}"
    
    # Получаем последние 3 хеша
    history = await _redis.lrange(key, 0, 2)
    
    # Если такой хеш уже есть — дубликат
    if msg_hash.encode() in history:
        return True
    
    # Добавляем новый хеш
    await _redis.lpush(key, msg_hash)
    await _redis.ltrim(key, 0, 2)  # Храним только 3 последних
    await _redis.expire(key, 600)  # 10 минут
    
    return False

# Система страйков
async def add_strike(tg_id: int) -> int:
    """Добавляет страйк, возвращает текущее количество"""
    if not _redis:
        return 0
    
    key = f"strikes:{tg_id}"
    strikes = await _redis.incr(key)
    if strikes == 1:
        await _redis.expire(key, 600)  # 10 минут
    
    return strikes

async def get_strikes(tg_id: int) -> int:
    """Возвращает текущее количество страйков"""
    if not _redis:
        return 0
    val = await _redis.get(f"strikes:{tg_id}")
    return int(val) if val else 0

async def is_auto_banned(tg_id: int) -> bool:
    """Проверяет автобан (3+ страйка)"""
    if not _redis:
        return False
    return await _redis.exists(f"autoban:{tg_id}")

async def auto_ban(tg_id: int, duration: int = 3600):
    """Автобан на duration секунд (по умолчанию 1 час)"""
    if not _redis:
        return
    await _redis.setex(f"autoban:{tg_id}", duration, "1")
    await _redis.delete(f"strikes:{tg_id}")

# Простая captcha
def generate_captcha() -> tuple[str, int]:
    """Генерирует простую математическую задачу"""
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    return f"{a} + {b} = ?", a + b

def captcha_keyboard(answer: int, tg_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами ответа (answer хранится в Redis, не в callback_data)"""
    # Правильный ответ + 3 неправильных
    options = [answer]
    while len(options) < 4:
        wrong = answer + random.randint(-5, 5)
        if wrong > 0 and wrong not in options:
            options.append(wrong)

    random.shuffle(options)

    buttons = [
        InlineKeyboardButton(text=str(opt), callback_data=f"captcha:{opt}")
        for opt in options
    ]

    return InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:]])

async def is_captcha_required(tg_id: int) -> bool:
    """Проверяет нужна ли captcha (первое обращение)"""
    if not _redis:
        return False
    
    key = f"captcha_passed:{tg_id}"
    passed = await _redis.exists(key)
    
    return not passed

async def mark_captcha_passed(tg_id: int):
    """Помечает что captcha пройдена"""
    if not _redis:
        return
    await _redis.setex(f"captcha_passed:{tg_id}", 86400 * 30, "1")  # 30 дней


async def store_captcha_answer(tg_id: int, answer: int, ttl: int = 120):
    """Сохраняет правильный ответ в Redis (не в callback_data)."""
    if not _redis:
        return
    await _redis.setex(f"captcha_answer:{tg_id}", ttl, str(answer))


async def verify_captcha_answer(tg_id: int, chosen: int) -> bool:
    """Проверяет ответ пользователя. Удаляет ключ после проверки."""
    if not _redis:
        return False
    key = f"captcha_answer:{tg_id}"
    correct = await _redis.get(key)
    if correct is None:
        return False  # expired or not set
    await _redis.delete(key)
    return str(chosen) == str(correct)
