"""Inline action keyboards for support topics."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def actions_keyboard(tg_id: int, last_order_id: int = None) -> InlineKeyboardMarkup:
    """Quick actions on the pinned client card."""
    kb = [
        [
            InlineKeyboardButton(text="💰 +50₽", callback_data=f"act:topup:{tg_id}:50"),
            InlineKeyboardButton(text="💰 +100₽", callback_data=f"act:topup:{tg_id}:100"),
            InlineKeyboardButton(text="💰 +200₽", callback_data=f"act:topup:{tg_id}:200"),
        ],
        [
            InlineKeyboardButton(text="🚫 Бан", callback_data=f"act:ban:{tg_id}"),
            InlineKeyboardButton(text="✅ Разбан", callback_data=f"act:unban:{tg_id}"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"act:refresh:{tg_id}"),
        ],
    ]
    if last_order_id:
        kb.append([
            InlineKeyboardButton(text=f"↩️ Вернуть #{last_order_id}", callback_data=f"act:refund:{last_order_id}"),
        ])
    kb.append([
        InlineKeyboardButton(text="📋 Шаблоны", callback_data="act:templates"),
        InlineKeyboardButton(text="🏷 Категория", callback_data="act:category"),
    ])
    kb.append([
        InlineKeyboardButton(text="🔒 Закрыть тикет", callback_data="close"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def category_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Оплата", callback_data="cat:payment"),
                InlineKeyboardButton(text="📦 Заказ", callback_data="cat:order_stuck"),
            ],
            [
                InlineKeyboardButton(text="↩️ Возврат", callback_data="cat:refund"),
                InlineKeyboardButton(text="❓ Вопрос", callback_data="cat:question"),
                InlineKeyboardButton(text="🤷 Другое", callback_data="cat:other"),
            ],
        ]
    )


def csat_keyboard(topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{i}⭐", callback_data=f"csat:{topic_id}:{i}")
                for i in range(1, 6)
            ]
        ]
    )


def auto_close_keyboard(topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, закрыть", callback_data=f"close_yes:{topic_id}"),
                InlineKeyboardButton(text="❌ Нужна помощь", callback_data=f"close_no:{topic_id}"),
            ]
        ]
    )


def close_confirm_keyboard(topic_id: int) -> InlineKeyboardMarkup:
    """Keyboard for manual close confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, закрыть", callback_data=f"close_yes:{topic_id}"),
                InlineKeyboardButton(text="❌ Нужна помощь", callback_data=f"close_no:{topic_id}"),
            ]
        ]
    )
