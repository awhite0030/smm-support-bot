import logging
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery
from aiogram.utils.markdown import hcode

from app.bot.handlers.private.windows import Window
from app.bot.manager import Manager
from app.bot.utils.redis import RedisStorage
from app.bot.utils.redis.models import UserData
from app.bot.utils.texts import SUPPORTED_LANGUAGES
from app.db import ticket_db

logger = logging.getLogger(__name__)

router = Router()
router.callback_query.filter(F.message.chat.type == "private", StateFilter(None))


@router.callback_query(F.data.startswith("close_yes:"))
async def close_yes_callback(call: CallbackQuery) -> None:
    """Handle client confirming ticket close from offer in private chat."""
    try:
        topic_id = int(call.data.split(":", 1)[1])
        logger.info("Private close_yes clicked for topic %s by user %s", topic_id, call.from_user.id)
        
        # Закрываем тикет
        await ticket_db.close_ticket(topic_id)
        
        await call.message.edit_text("✅ Тикет закрыт. Хорошего дня!")
        await call.answer()
        
        # Отправляем CSAT оценку клиенту
        from app.bot.utils.action_keyboard import csat_keyboard
        try:
            await call.bot.send_message(
                call.from_user.id,
                "🙏 Пожалуйста, оцените работу поддержки от 1 до 5:",
                reply_markup=csat_keyboard(topic_id),
            )
        except Exception as e:
            logger.warning("Failed to send CSAT to user %s: %s", call.from_user.id, e)
    except Exception as e:
        logger.error("Private close_yes_callback failed for %s: %s", call.data, e, exc_info=True)
        try:
            await call.answer("Ошибка при закрытии тикета", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("close_no:"))
async def close_no_callback(call: CallbackQuery) -> None:
    """Handle client requesting more help from offer in private chat."""
    try:
        topic_id = int(call.data.split(":", 1)[1])
        logger.info("Private close_no clicked for topic %s", topic_id)
        
        # Сбрасываем таймер автозакрытия (клиент ещё пишет)
        await ticket_db.touch_user_msg(topic_id)
        
        await call.message.edit_text("Хорошо, оператор скоро ответит. ⏳")
        await call.answer()
    except Exception as e:
        logger.error("Private close_no_callback failed for %s: %s", call.data, e, exc_info=True)
        try:
            await call.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@router.callback_query()
async def handler(call: CallbackQuery, manager: Manager, redis: RedisStorage, user_data: UserData) -> None:
    """
    Handles callback queries for selecting the language.

    If the callback data is 'ru' or 'en', updates the user's language code in Redis and sets
    the language for the manager's text messages. Then, displays the main menu window.

    :param call: CallbackQuery object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param user_data: UserData object.
    :return: None
    """
    if call.data in SUPPORTED_LANGUAGES.keys():
        user_data.language_code = call.data
        manager.text_message.language_code = call.data
        await redis.update_user(user_data.id, user_data)
        await manager.state.update_data(language_code=call.data)
        await Window.main_menu(manager)

    await call.answer()
