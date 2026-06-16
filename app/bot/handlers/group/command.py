from contextlib import suppress

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, MagicData
from aiogram.types import Message
from aiogram.utils.markdown import hcode, hbold

from app.bot.manager import Manager
from app.bot.utils.redis import RedisStorage
from app.bot.utils.shop_db import (
    render_shop_card,
    render_order_card,
    block_user as shop_block_user,
    topup_balance as shop_topup,
    refund_order as shop_refund,
    refresh_order as shop_refresh,
)
from app.db import tickets as ticket_db
from app.bot.filters import IsGroupAdmin

router_id = Router()
router_id.message.filter(
    F.chat.type.in_(["group", "supergroup"]),
)


@router_id.message(Command("id"))
async def handler(message: Message) -> None:
    """
    Sends chat ID in response to the /id command.

    :param message: Message object.
    :return: None
    """
    await message.reply(hcode(message.chat.id))


router = Router()
router.message.filter(
    F.message_thread_id.is_not(None),
    F.chat.type.in_(["group", "supergroup"]),
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
)


@router.message(Command("silent"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Toggles silent mode for a user in the group.
    If silent mode is disabled, it will be enabled, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.message_silent_mode:
        text = manager.text_message.get("silent_mode_disabled")
        with suppress(TelegramBadRequest):
            # Reply with the specified text
            await message.reply(text)

            # Unpin the chat message with the silent mode status
            await message.bot.unpin_chat_message(
                chat_id=message.chat.id,
                message_id=user_data.message_silent_id,
            )

        user_data.message_silent_mode = False
        user_data.message_silent_id = None
    else:
        text = manager.text_message.get("silent_mode_enabled")
        with suppress(TelegramBadRequest):
            # Reply with the specified text
            msg = await message.reply(text)

            # Pin the chat message with the silent mode status
            await msg.pin(disable_notification=True)

        user_data.message_silent_mode = True
        user_data.message_silent_id = msg.message_id

    await redis.update_user(user_data.id, user_data)


@router.message(Command("information"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """Расширенная карточка клиента: tg-данные + контекст из магазина и сводка тикетов."""
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa
    format_data = user_data.to_dict()
    format_data["full_name"] = hbold(format_data["full_name"])
    base = manager.text_message.get("user_information").format_map(format_data)
    try:
        from app.bot.utils.shop_db import render_information_extras
        extras = await render_information_extras(user_data.id)
    except Exception as e:
        extras = None
    text = base + ("\n" + extras if extras else "")
    await message.reply(text, disable_web_page_preview=True)


@router.message(Command("shop"))
async def shop_handler(message: Message, redis: RedisStorage) -> None:
    """Show shop client card for the user this topic is about."""
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data:
        return None  # noqa
    card = await render_shop_card(user_data.id)
    if card:
        await message.reply(card, disable_web_page_preview=True)
    else:
        await message.reply("ℹ️ Этот пользователь не найден в базе магазина.")


@router.message(Command("order"))
async def order_handler(message: Message) -> None:
    """Show order details by uid: /order O12345678"""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: <code>/order O12345678</code>")
        return
    uid = parts[1].strip()
    card = await render_order_card(uid)
    if card:
        await message.reply(card, disable_web_page_preview=True)
    else:
        await message.reply(f"❌ Заказ <code>{uid}</code> не найден.")


@router.message(Command(commands=["ban"]), IsGroupAdmin())
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """Toggle ban in support AND in shop database."""
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.is_banned:
        user_data.is_banned = False
        text = manager.text_message.get("user_unblocked")
    else:
        user_data.is_banned = True
        text = manager.text_message.get("user_blocked")

    await message.reply(text)
    await redis.update_user(user_data.id, user_data)

    res = await shop_block_user(user_data.id)
    if res.get("ok"):
        new_state = res.get("data", ).get("is_blocked")
        await message.reply(
            f"🛒 Магазин: {'🚫 заблокирован' if new_state else '✅ разблокирован'}"
        )
    else:
        await message.reply(f"⚠️ Магазин не обновлён: {res.get('error','?')}")


@router.message(Command(commands=["refund"]), IsGroupAdmin())
async def refund_handler(message: Message, redis: RedisStorage) -> None:
    """/refund <order_id> — refund order back to user balance via shop API."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: <code>/refund 123</code>")
        return
    oid_raw = parts[1].strip().lstrip("#")
    if not oid_raw.isdigit():
        await message.reply("Номер заказа должен быть числом.")
        return
    oid = int(oid_raw)
    res = await shop_refund(oid)
    if res.get("ok"):
        await message.reply(f"✅ Заказ #{oid} возвращён клиенту.")
    else:
        await message.reply(
            f"❌ Возврат не выполнен: {res.get('error', res.get('status', '?'))}"
        )


@router.message(Command(commands=["refresh"]), IsGroupAdmin())
async def refresh_handler(message: Message) -> None:
    """/refresh <order_id> — pull latest status from upstream provider."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: <code>/refresh 123</code>")
        return
    oid_raw = parts[1].strip().lstrip("#")
    if not oid_raw.isdigit():
        await message.reply("Номер заказа должен быть числом.")
        return
    res = await shop_refresh(int(oid_raw))
    if res.get("ok"):
        await message.reply(f"🔄 Заказ обновлён: <code>{res.get('data')}</code>")
    else:
        await message.reply(f"❌ {res.get('error', res.get('status', '?'))}")


@router.message(Command(commands=["topup"]), IsGroupAdmin())
async def topup_handler(message: Message, redis: RedisStorage) -> None:
    """/topup <amount> [comment] — credit/debit user's balance."""
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.reply(
            "Использование: <code>/topup 100</code> или <code>/topup -50 ошибочно</code>"
        )
        return
    try:
        amount = float(parts[1].replace(",", "."))
    except ValueError:
        await message.reply("Сумма должна быть числом, например <code>100</code>")
        return
    comment = parts[2] if len(parts) > 2 else "support adjustment"
    res = await shop_topup(user_data.id, amount, comment)
    if res.get("ok"):
        new_bal = res.get("data", ).get("balance")
        sign = "+" if amount >= 0 else ""
        await message.reply(
            f"💳 Баланс изменён: <b>{sign}{amount:g} ₽</b>\n"
            f"Новый баланс: <b>{new_bal} ₽</b>"
        )
    else:
        await message.reply(f"❌ {res.get('error', res.get('status', '?'))}")


@router.message(Command(commands=["close", "closed"]), IsGroupAdmin())
async def close_handler(message: Message, redis: RedisStorage) -> None:
    """Close a ticket from the topic. Triggers CSAT survey to the user."""
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa
    await ticket_db.close_ticket(message.message_thread_id)
    await message.reply("✅ Тикет закрыт. Отправляю клиенту уведомление.")

    user_data.message_thread_id = None
    await redis.update_user(user_data.id, user_data)

    # notify user that ticket is closed
    try:
        await message.bot.send_message(
            user_data.id,
            "✅ <b>Ваш тикет закрыт</b>\n\nСпасибо за обращение! Если у вас возникнут ещё вопросы, пишите — мы всегда на связи.",
        )
    except Exception:
        pass

    # ask CSAT in the user's DM (only once per ticket)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    try:
        already = await ticket_db.is_csat_asked(message.message_thread_id)
        if already:
            return  # CSAT already sent for this ticket
        await ticket_db.mark_csat_asked(message.message_thread_id)
    except Exception:
        pass
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=str(i) + "⭐", callback_data=f"csat:{message.message_thread_id}:{i}")
        for i in range(1, 6)
    ]])
    try:
        await message.bot.send_message(
            user_data.id,
            "🙏 Пожалуйста, оцените работу поддержки от 1 до 5:",
            reply_markup=kb,
        )
    except Exception:
        pass


@router.message(Command(commands=["stats"]))
async def stats_handler(message: Message) -> None:
    """Support team stats."""
    s = await ticket_db.stats()
    avg = s.get("avg_csat")
    await message.reply(
        "📊 <b>Поддержка</b>\\n\\n"
        f"Открытых: <b>{s.get('open') or 0}</b>\\n"
        f"Закрытых сегодня: <b>{s.get('closed_today') or 0}</b>\\n\\n"
        f"⏱ Среднее время ответа: <b>{(s.get('avg_response_sec') or 0) // 60} мин</b>\\n"
        f"⭐ Средний CSAT: <b>{f'{avg:.2f}' if avg else '—'}</b>"
    )


# ──────────────────────────────────────────────────────────────
#  Templates
# ──────────────────────────────────────────────────────────────
@router.message(Command(commands=["templates", "tpl_list"]))
async def templates_list(message: Message) -> None:
    items = await ticket_db.list_templates(only_active=True)
    if not items:
        await message.reply("Шаблоны не созданы. Добавьте в админке.")
        return
    lines = ["📋 <b>Шаблоны ответов</b>", ""]
    for t in items:
        lines.append(f"• <code>/t {t['slug']}</code> — {t['title']}")
    lines.append("")
    lines.append("Использование: <code>/t &lt;slug&gt;</code>")
    await message.reply("\n".join(lines))


@router.message(Command(commands=["t", "tpl"]))
async def template_use(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: <code>/t &lt;slug&gt;</code>")
        return
    slug = parts[1].strip().lower()
    tpl = await ticket_db.get_template(slug)
    if not tpl:
        await message.reply(f"Шаблон <code>{slug}</code> не найден.")
        return
    # Отправим как обычное сообщение в топик — бот пересылает в личку клиенту
    # (логика пересылки в handlers/group/message.py)
    await message.answer(tpl["text"])
    with suppress(TelegramBadRequest):
        await message.delete()


# ──────────────────────────────────────────────────────────────
#  Assign / escalate
# ──────────────────────────────────────────────────────────────
@router.message(Command(commands=["assign"]), IsGroupAdmin())
async def assign_handler(message: Message) -> None:
    if not message.message_thread_id:
        return
    # /assign @username  или  /assign 123456
    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) >= 2:
            arg = parts[1].strip().lstrip("@")
            if arg.isdigit():
                target_id = int(arg)
    if not target_id:
        await message.reply("Использование: ответьте на сообщение оператора /assign или /assign &lt;id&gt;")
        return
    await ticket_db.set_assignee(message.message_thread_id, target_id)
    await ticket_db.log_action(
        message.message_thread_id, None, message.from_user.id if message.from_user else None,
        "assign", {"operator_id": target_id},
    )
    await message.reply(f"✅ Тикет назначен на оператора <code>{target_id}</code>")


@router.message(Command(commands=["category"]), IsGroupAdmin())
async def category_handler(message: Message) -> None:
    if not message.message_thread_id:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "Использование: <code>/category &lt;payment|order_stuck|refund|question|other&gt;</code>"
        )
        return
    cat = parts[1].strip().lower()
    allowed = {"payment", "order_stuck", "refund", "question", "other"}
    if cat not in allowed:
        await message.reply(f"Допустимые категории: {', '.join(sorted(allowed))}")
        return
    await ticket_db.set_category(message.message_thread_id, cat)
    await message.reply(f"🏷 Категория тикета: <b>{cat}</b>")
