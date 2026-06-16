import asyncio

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import StateFilter
from aiogram.types import Message

from app.bot.manager import Manager
from app.bot.types.album import Album
from app.bot.utils.create_forum_topic import (
    create_forum_topic,
    get_or_create_forum_topic,
)
from app.bot.utils.redis import RedisStorage
from app.bot.utils.redis.models import UserData
from app.db import ticket_db


async def _delete_after(msg, delay: int) -> None:
    """Delete a message after `delay` seconds, ignoring failures."""
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass

router = Router()
router.message.filter(F.chat.type == "private", StateFilter(None))


@router.edited_message()
async def handle_edited_message(message: Message, manager: Manager) -> None:
    """
    Handle edited messages.

    :param message: The edited message.
    :param manager: Manager object.
    :return: None
    """
    # Get the text for the edited message
    text = manager.text_message.get("message_edited")
    # Reply to the edited message with the specified text
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    asyncio.create_task(_delete_after(msg, 5))


@router.message(F.media_group_id)
@router.message(F.media_group_id.is_(None))
async def handle_incoming_message(
        message: Message,
        manager: Manager,
        redis: RedisStorage,
        user_data: UserData,
        album: Album | None = None,
) -> None:
    """
    Handles incoming messages and copies them to the forum topic.
    If the user is banned, the messages are ignored.

    :param message: The incoming message.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param user_data: UserData object.
    :param album: Album object or None.
    :return: None
    """
    # Check if the user is banned
    if user_data.is_banned:
        return

    # Check for duplicate messages (anti-spam)
    text = message.text or message.caption or ""
    if text:
        try:
            from app.antispam import is_duplicate_message, add_strike, auto_ban, get_strikes
            if await is_duplicate_message(message.from_user.id, text):
                strikes = await add_strike(message.from_user.id)
                if strikes >= 3:
                    await auto_ban(message.from_user.id, duration=3600)
                    await message.answer("🚫 Вы забанены на 1 час за спам.")
                    return
                await message.answer(f"⚠️ Не отправляйте одинаковые сообщения подряд. ({strikes}/3)")
                return
        except Exception:
            pass  # antispam failure should not block messages

    async def copy_message_to_topic():
        """
        Copies the message or album to the forum topic.
        If no album is provided, the message is copied. Otherwise, the album is copied.
        """
        # Лимит открытых тикетов
        open_count = await ticket_db.count_open_tickets(message.from_user.id)
        if open_count >= 3:
            await message.answer("⚠️ У вас уже открыто 3 тикета. Дождитесь ответа или закройте один из них.")
            return
        
        message_thread_id = await get_or_create_forum_topic(
            message.bot,
            redis,
            manager.config,
            user_data,
        )

        if not album:
            await message.forward(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=message_thread_id,
            )
        else:
            await album.copy_to(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=message_thread_id,
            )

    try:
        await copy_message_to_topic()
        try:
            if user_data.message_thread_id:
                await ticket_db.mark_user_msg(user_data.message_thread_id)
        except Exception:
            pass
    except TelegramNetworkError:
        # Telegram API timeout — message queued, will be delivered later
        # Don't crash — let user know we received it
        text = manager.text_message.get("message_sent") or "✅ Сообщение получено, скоро ответим."
        try:
            msg = await message.reply(text)
            asyncio.create_task(_delete_after(msg, 5))
        except Exception:
            pass
        return
    except TelegramBadRequest as ex:
        if "message thread not found" in ex.message:
            user_data.message_thread_id = await create_forum_topic(
                message.bot,
                manager.config,
                user_data.full_name,
            )
            await redis.update_user(user_data.id, user_data)
            await copy_message_to_topic()
        else:
            raise

    # Send a confirmation message to the user
    text = manager.text_message.get("message_sent")
    # Reply to the edited message with the specified text
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    asyncio.create_task(_delete_after(msg, 5))
