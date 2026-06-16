import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.config import Config
from .exceptions import CreateForumTopicException, NotEnoughRightsException, NotAForumException
from .redis import RedisStorage
from .redis.models import UserData


async def get_or_create_forum_topic(
        bot: Bot,
        redis: RedisStorage,
        config: Config,
        user_data: UserData,
) -> int:
    if user_data.message_thread_id is None:
        # Try to reopen a recently-closed ticket (< 24h) before creating a new topic
        try:
            from app.db import tickets as ticket_db
            existing_topic_id = await ticket_db.reopen_recent_ticket(user_data.id, hours=24)
            if existing_topic_id:
                user_data.message_thread_id = existing_topic_id
                await redis.update_user(user_data.id, user_data)
                return existing_topic_id
        except Exception as r_err:
            logging.warning(f"ticket reopen failed: {r_err}")

        try:
            # If no recent ticket, create a new forum topic
            message_thread_id = await create_forum_topic(
                bot, config, user_data.full_name,
            )
            user_data.message_thread_id = message_thread_id
            await redis.update_user(user_data.id, user_data)

            try:
                from app.db import tickets as ticket_db
                await ticket_db.upsert_ticket(user_data.id, message_thread_id)
            except Exception as t_err:
                logging.warning(f"ticket db register failed: {t_err}")

            # Pin shop card + extras + actions
            try:
                from .shop_db import render_shop_card, render_information_extras, fetch_user_summary
                from app.bot.utils.action_keyboard import actions_keyboard
                card = await render_shop_card(user_data.id)
                extras = await render_information_extras(user_data.id)
                summary = await fetch_user_summary(user_data.id)
                last_order_id = None
                if summary and summary.get('last_orders'):
                    last_order_id = summary['last_orders'][0].get('id')
                full = (card or "") + ("\n" + extras if extras else "")
                if full.strip():
                    sent = await bot.send_message(
                        chat_id=config.bot.GROUP_ID,
                        message_thread_id=message_thread_id,
                        text=full,
                        disable_web_page_preview=True,
                        reply_markup=actions_keyboard(user_data.id, last_order_id),
                    )
                    try:
                        await bot.pin_chat_message(
                            chat_id=config.bot.GROUP_ID,
                            message_id=sent.message_id,
                            disable_notification=True,
                        )
                    except Exception:
                        pass
            except Exception as shop_err:
                logging.warning(f"shop card render failed: {shop_err}")

            # ask the user for category in DM
            try:
                from app.bot.handlers.private.extras import category_keyboard
                await bot.send_message(
                    user_data.id,
                    "🆘 Чтобы оператор быстрее сориентировался, выберите тему:",
                    reply_markup=category_keyboard(message_thread_id),
                )
            except Exception:
                pass

        except Exception as e:
            await bot.send_message(config.bot.DEV_ID, str(e))
            logging.exception(e)

    return user_data.message_thread_id


async def create_forum_topic(bot: Bot, config: Config, name: str, max_retries: int = 5) -> int:
    """
    Creates a forum topic in the specified chat.

    :param bot: The Aiogram Bot instance.
    :param config: The configuration object.
    :param name: The name of the forum topic.
    :param max_retries: Maximum number of retries on rate limit.

    :return: The message thread ID of the created forum topic.
    :raises NotEnoughRightsException: If the bot doesn't have enough rights to create a forum topic.
    :raises CreateForumTopicException: If an error occurs while creating a forum topic.
    """
    attempt = 0
    while attempt < max_retries:
        try:
            # Attempt to create a forum topic
            forum_topic = await bot.create_forum_topic(
                chat_id=config.bot.GROUP_ID,
                name=name,
                icon_custom_emoji_id=config.bot.BOT_EMOJI_ID,
                request_timeout=30,
            )
            return forum_topic.message_thread_id

        except TelegramRetryAfter as ex:
            # Handle Retry-After exception (rate limiting)
            attempt += 1
            logging.warning(
                "create_forum_topic rate limited (attempt %d/%d): %s",
                attempt, max_retries, ex.message,
            )
            if attempt >= max_retries:
                raise CreateForumTopicException(
                    f"Rate limited {max_retries} times, giving up",
                )
            await asyncio.sleep(ex.retry_after)

        except TelegramBadRequest as ex:
            if "not enough rights" in ex.message:
                # Raise an exception if the bot doesn't have enough rights
                raise NotEnoughRightsException

            elif "not a forum" in ex.message:
                # Raise an exception if the chat is not a forum
                raise NotAForumException

            # Raise a generic exception for other cases
            raise CreateForumTopicException

        except Exception as ex:
            # Re-raise any other exceptions
            raise ex

    raise CreateForumTopicException("Max retries exceeded")
