"""Background jobs: SLA alerts + auto-close + CSAT request."""
from __future__ import annotations

import logging
import os
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db import tickets as ticket_db

logger = logging.getLogger(__name__)

SLA_ALERT_MINUTES = int(os.getenv("SUPPORT_SLA_MINUTES", "30"))
AUTO_CLOSE_HOURS = int(os.getenv("SUPPORT_AUTO_CLOSE_HOURS", "24"))


async def sla_alert_job(bot: Bot, config: Any) -> None:
    """Ping support team about tickets that wait too long."""
    try:
        breaching = await ticket_db.stale_open_tickets(SLA_ALERT_MINUTES)
    except Exception:
        logger.exception("sla check failed")
        return
    for t in breaching:
        try:
            await bot.send_message(
                chat_id=t.get("group_id") or config.bot.GROUP_ID,
                message_thread_id=t["topic_id"],
                text=(
                    f"⏰ <b>SLA-алёрт</b>\n"
                    f"Клиенту не ответили дольше {SLA_ALERT_MINUTES} минут."
                ),
            )
            # Mark as alerted so we don't spam
            await ticket_db.mark_sla_alerted(t["id"])
        except Exception as e:
            logger.warning("sla alert send failed: %s", e)


async def auto_close_job(bot: Bot, config: Any) -> None:
    """Auto-close pending tickets and ask CSAT in DM (only once per ticket)."""
    try:
        candidates = await ticket_db.autoclose_idle(AUTO_CLOSE_HOURS)
    except Exception:
        logger.exception("auto close check failed")
        return
    for t in candidates:
        topic_id = t["topic_id"]
        tg_id = t["user_id"]
        # Check CSAT not already sent (via DB flag)
        try:
            already = await ticket_db.is_csat_asked(topic_id)
            if already:
                continue  # CSAT already sent, skip
        except Exception:
            pass
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"{i}⭐", callback_data=f"csat:{topic_id}:{i}"
                ) for i in range(1, 6)
            ]])
            await bot.send_message(
                tg_id,
                "🙏 Если ваш вопрос решён — оцените, пожалуйста, работу поддержки:",
                reply_markup=kb,
            )
            await ticket_db.mark_csat_asked(topic_id)
            try:
                await bot.send_message(
                    chat_id=t.get("group_id") or config.bot.GROUP_ID,
                    message_thread_id=topic_id,
                    text="✅ Тикет авто-закрыт по таймауту. Клиенту отправлен опрос.",
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("auto close failed for topic %s: %s", topic_id, e)


async def offer_close_job(bot, config) -> None:
    """Offer auto-close 1h before deadline."""
    try:
        from app.db import tickets as ticket_db
        from app.bot.utils.action_keyboard import auto_close_keyboard

        pending = await ticket_db.tickets_pending_close_offer(hours_before=1, auto_close_h=24)
        for t in pending:
            try:
                await bot.send_message(
                    t["user_id"],  # FIX: column is user_id, not tg_id
                    "Ваш вопрос решён? Если да — тикет автоматически закроется через час.",
                    reply_markup=auto_close_keyboard(t["topic_id"]),
                )
                await ticket_db.mark_close_offered(t["topic_id"])
            except Exception as e:
                logger.warning("offer_close failed for %s: %s", t["topic_id"], e)
    except Exception as e:
        logger.error("offer_close_job failed: %s", e)
