"""Group callback handlers for action buttons."""
import logging
from contextlib import suppress

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from app.bot.utils.shop_db import (
    topup_balance,
    block_user,
    render_shop_card,
    render_information_extras,
)
from app.bot.utils.action_keyboard import actions_keyboard, category_choice_keyboard
from app.db import tickets as ticket_db
from app.bot.utils.redis.redis import RedisStorage

logger = logging.getLogger(__name__)

router = Router(name="group_callback")


@router.callback_query(F.data.startswith("act:"))
async def action_callback(call: CallbackQuery) -> None:
    await call.answer()
    if not call.message or not call.message.message_thread_id:
        return
    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    tg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    if action == "topup" and len(parts) >= 4:
        amount = int(parts[3])
        try:
            res = await topup_balance(tg_id, amount, f"support topup by {call.from_user.id if call.from_user else 'unknown'}")
            if res.get("ok"):
                await call.message.answer(f"✅ Пополнено +{amount}₽")
                await ticket_db.log_action(
                    call.message.message_thread_id, tg_id, call.from_user.id if call.from_user else None,
                    "topup", {"amount": amount},
                )
            else:
                await call.message.answer(f"❌ Ошибка: {res.get('error', 'unknown')}")
        except Exception as e:
            await call.message.answer(f"❌ Ошибка: {str(e)}")

    elif action == "ban":
        try:
            res = await block_user(tg_id)
            if res.get("ok"):
                await call.message.answer("🚫 Статус блокировки переключён (toggle). Проверьте результат.")
                await ticket_db.log_action(
                    call.message.message_thread_id, tg_id, call.from_user.id if call.from_user else None,
                    "ban", {},
                )
            else:
                await call.message.answer(f"❌ Ошибка: {res.get('error')}")
        except Exception as e:
            await call.message.answer(f"❌ Ошибка: {str(e)}")

    elif action == "unban":
        try:
            res = await block_user(tg_id)
            if res.get("ok"):
                await call.message.answer("✅ Статус блокировки переключён (toggle). Проверьте результат.")
                await ticket_db.log_action(
                    call.message.message_thread_id, tg_id, call.from_user.id if call.from_user else None,
                    "unban", {},
                )
            else:
                await call.message.answer(f"❌ Ошибка: {res.get('error')}")
        except Exception as e:
            await call.message.answer(f"❌ Ошибка: {str(e)}")

    elif action == "refund" and len(parts) >= 3:
        order_id = int(parts[2])
        try:
            from app.bot.utils.shop_db import refund_order
            res = await refund_order(order_id)
            if res.get("ok"):
                await call.message.answer(f"✅ Возврат за заказ #{order_id} выполнен")
                await ticket_db.log_action(
                    call.message.message_thread_id, tg_id, call.from_user.id if call.from_user else None,
                    "refund", {"order_id": order_id},
                )
            else:
                await call.message.answer(f"❌ Ошибка: {res.get('error', 'unknown')}")
        except Exception as e:
            await call.message.answer(f"❌ Ошибка: {str(e)}")

    elif action == "refresh":
        try:
            card = await render_shop_card(tg_id)
            extras = await render_information_extras(tg_id)
            full = (card or "") + ("\n" + extras if extras else "")
            if full.strip():
                with suppress(TelegramBadRequest):
                    await call.message.edit_text(
                        full,
                        reply_markup=actions_keyboard(tg_id),
                        disable_web_page_preview=True,
                    )
            await call.answer("Обновлено")
        except Exception as e:
            await call.answer(f"Ошибка: {str(e)}", show_alert=True)

    elif action == "templates":
        items = await ticket_db.list_templates(only_active=True)
        if not items:
            await call.answer("Шаблоны не созданы", show_alert=True)
            return
        lines = ["📋 <b>Шаблоны</b>", ""]
        for t in items:
            lines.append(f"• <code>/t {t['slug']}</code> — {t['title']}")
        await call.message.answer("\n".join(lines))
        await call.answer()

    elif action == "category":
        await call.message.answer(
            "🏷 Выберите категорию тикета:",
            reply_markup=category_choice_keyboard(),
        )
        await call.answer()


@router.callback_query(F.data.startswith("cat:"))
async def category_callback(call: CallbackQuery) -> None:
    await call.answer()
    if not call.message or not call.message.message_thread_id:
        return
    cat = call.data.split(":", 1)[1] if ":" in call.data else "other"
    await ticket_db.set_category(call.message.message_thread_id, cat)
    await call.message.edit_text(f"🏷 Категория: <b>{cat}</b>")


@router.callback_query(F.data.startswith("csat:"))
async def csat_callback(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer()
        return
    try:
        topic_id = int(parts[1])
        score = int(parts[2])
    except (ValueError, TypeError):
        await call.answer("Ошибка", show_alert=True)
        return
    if score < 1 or score > 5:
        await call.answer("Оценка от 1 до 5", show_alert=True)
        return
    await ticket_db.set_csat(topic_id, score)
    try:
        await call.message.edit_text(f"Спасибо за оценку! {score}⭐")
    except TelegramBadRequest:
        pass  # message not modified or already deleted
    await call.answer("Оценка сохранена")


@router.callback_query(F.data.startswith("close_yes:"))
async def close_yes_callback(call: CallbackQuery, redis: RedisStorage) -> None:
    """Handle agent confirming ticket close from group chat."""
    try:
        topic_id = int(call.data.split(":", 1)[1])
        logger.info("close_yes clicked for topic %s by %s", topic_id, call.from_user.id)
        
        # Получаем user_id ДО закрытия тикета
        pool = await ticket_db.get_pool()
        user_id = None
        if pool:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT user_id FROM support.tickets WHERE topic_id=$1",
                    topic_id
                )
                if row:
                    user_id = row["user_id"]
        
        # Закрываем тикет
        await ticket_db.close_ticket(topic_id)
        logger.info("Ticket %s closed, user_id=%s", topic_id, user_id)
        
        await call.message.edit_text("✅ Тикет закрыт. Хорошего дня!")
        await call.answer()
        
        # Отправляем оценку клиенту в личку
        if user_id:
            from app.bot.utils.action_keyboard import csat_keyboard
            try:
                await call.bot.send_message(
                    user_id,
                    "🙏 Пожалуйста, оцените работу поддержки от 1 до 5:",
                    reply_markup=csat_keyboard(topic_id),
                )
            except Exception as e:
                logger.warning("Failed to send CSAT to user %s: %s", user_id, e)
    except Exception as e:
        logger.error("close_yes_callback failed for %s: %s", call.data, e, exc_info=True)
        await call.answer("Ошибка при закрытии тикета", show_alert=True)


@router.callback_query(F.data.startswith("close_no:"))
async def close_no_callback(call: CallbackQuery) -> None:
    """Handle agent declining close from group chat."""
    try:
        topic_id = int(call.data.split(":", 1)[1])
        logger.info("close_no clicked for topic %s", topic_id)
        # Reset last_user_msg_at to extend auto-close window
        await ticket_db.touch_user_msg(topic_id)
        await call.message.edit_text("Хорошо, оператор скоро ответит.")
        await call.answer()
    except Exception as e:
        logger.error("close_no_callback failed for %s: %s", call.data, e, exc_info=True)
        await call.answer("Ошибка", show_alert=True)


@router.callback_query(F.data == "close")
async def close_button_callback(call: CallbackQuery) -> None:
    """Handle close button - show confirmation"""
    if not call.message or not call.message.message_thread_id:
        await call.answer()
        return
    
    from app.bot.utils.action_keyboard import close_confirm_keyboard
    await call.message.answer(
        "❓ Вопрос решён?",
        reply_markup=close_confirm_keyboard(call.message.message_thread_id),
    )
    await call.answer()
