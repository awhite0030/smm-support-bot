"""FAQ menu, ticket category picker, CSAT rating."""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from app.bot.utils.redis import RedisStorage
from app.bot.utils.redis.models import UserData
from app.db import tickets as ticket_db

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


# ─── FAQ ────────────────────────────────────────────────────────────────────

async def _faq_keyboard(redis: RedisStorage = None, user_id: int = None) -> InlineKeyboardMarkup:
    lang = "ru"
    if redis and user_id:
        try:
            user_data = await redis.get_user(user_id)
            if user_data and user_data.language_code:
                lang = user_data.language_code[:2]
        except Exception:
            pass
    items = await ticket_db.list_faq()
    rows = [
        [InlineKeyboardButton(text=f["question"], callback_data=f"faq:{f['slug']}")]
        for f in items
    ]
    rows.append([
        InlineKeyboardButton(text="✍️ Написать оператору", callback_data="faq:human")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("faq"), StateFilter(None))
async def faq_command(message: Message, redis: RedisStorage) -> None:
    kb = await _faq_keyboard(redis=redis, user_id=message.from_user.id)
    await message.answer(
        "❓ <b>Часто задаваемые вопросы</b>\n\n"
        "Выберите тему — возможно ответ уже есть. Если нет, нажмите "
        "<i>Написать оператору</i>.",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("faq:") & (F.data != "faq:menu"))
async def faq_callback(call: CallbackQuery) -> None:
    slug = call.data.split(":", 1)[1]
    if slug == "human":
        await call.message.edit_text(
            "✍️ Просто напишите вопрос в этот чат — оператор увидит и ответит. "
            "В первое сообщение постарайтесь добавить:\n"
            "• номер заказа (если есть)\n"
            "• ссылку, на которую делалась накрутка\n"
            "• что именно пошло не так"
        )
        await call.answer()
        return
    item = await ticket_db.get_faq(slug)
    if not item:
        await call.answer("Не найдено", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ К списку", callback_data="faq:menu"),
        InlineKeyboardButton(text="✍️ Оператор", callback_data="faq:human"),
    ]])
    await call.message.edit_text(
        f"<b>{item['question']}</b>\n\n{item['answer']}", reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "faq:menu")
async def faq_back(call: CallbackQuery, redis: RedisStorage) -> None:
    kb = await _faq_keyboard(redis=redis, user_id=call.from_user.id)
    await call.message.edit_text(
        "❓ <b>Часто задаваемые вопросы</b>\n\nВыберите тему:",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "faq:human")
async def faq_human(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "✅ Тема передана оператору",
    )
    await call.answer()


# ─── Category picker (set on first user message) ───────────────────────────

CATEGORIES = [
    ("payment", "💳 Оплата / пополнение"),
    ("order_stuck", "⏳ Заказ не выполнен"),
    ("refund", "💰 Возврат денег"),
    ("question", "❓ Вопрос по товару"),
    ("other", "🗒 Другое"),
]


def category_keyboard(topic_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"cat:{topic_id}:{slug}")]
        for slug, label in CATEGORIES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("cat:"))
async def category_callback(call: CallbackQuery) -> None:
    try:
        _, topic_id, slug = call.data.split(":", 2)
        topic_id = int(topic_id)
    except Exception:
        await call.answer()
        return
    label = dict(CATEGORIES).get(slug, slug)
    await ticket_db.set_category(topic_id, slug)
    try:
        await call.message.edit_text(
            f"✅ Тема: <b>{label}</b>\n\nОператор уже видит ваше сообщение и скоро ответит."
        )
    except Exception:
        pass
    await call.answer()


# ─── CSAT (1..5) ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("csat:"))
async def csat_callback(call: CallbackQuery, user_data: UserData) -> None:
    try:
        _, topic_id, score = call.data.split(":", 2)
        topic_id = int(topic_id)
        score = int(score)
    except Exception:
        await call.answer()
        return
    if score < 1 or score > 5:
        await call.answer()
        return
    await ticket_db.set_csat(topic_id, score)
    text = "Спасибо! 🙏" if score >= 4 else "Спасибо за честность! Постараемся быть лучше."
    try:
        await call.message.edit_text(
            f"{'⭐' * score}\n\n{text}"
        )
    except Exception:
        pass
    # post score to the topic so the team sees it
    try:
        from app.config import load_config
        cfg = load_config()
        await call.bot.send_message(
            chat_id=cfg.bot.GROUP_ID,
            message_thread_id=topic_id,
            text=f"⭐ Клиент оценил поддержку: <b>{score}/5</b>",
        )
    except Exception:
        pass
    await call.answer()
