"""Custom aiogram filters for the support bot."""
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from app.config import Config


class IsGroupAdmin(BaseFilter):
    """Check if the user is an admin (or creator) of the support group.

    Usage:
        @router.message(Command("topup"), IsGroupAdmin())
        async def topup_handler(message: Message):
            ...
    """

    def __init__(self, config: Config | None = None):
        self._config = config

    async def __call__(self, event: Message | CallbackQuery, config: Config) -> bool:
        if not event.from_user:
            return False
        group_id = config.bot.GROUP_ID
        dev_id = config.bot.DEV_ID

        # Developer always has access
        if event.from_user.id == dev_id:
            return True

        try:
            member = await event.bot.get_chat_member(
                chat_id=group_id,
                user_id=event.from_user.id,
            )
            return member.status in ("administrator", "creator")
        except Exception:
            return False
