import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

log = logging.getLogger(__name__)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .bot import commands
from .bot.handlers import include_routers
from .bot.middlewares import register_middlewares
from .config import load_config, Config
from .security import init_security, PII_Filter
from .logger import setup_logger


async def on_shutdown(
    apscheduler: AsyncIOScheduler,
    dispatcher: Dispatcher,
    config: Config,
    bot: Bot,
) -> None:
    """
    Shutdown event handler. This runs when the bot shuts down.

    :param apscheduler: AsyncIOScheduler: The apscheduler instance.
    :param dispatcher: Dispatcher: The bot dispatcher.
    :param config: Config: The config instance.
    :param bot: Bot: The bot instance.
    """
    # Stop API server gracefully
    api_server = dispatcher.get("_api_server")
    if api_server and not api_server.should_exit:
        api_server.should_exit = True
    # Stop apscheduler
    apscheduler.shutdown()
    # Delete commands and close storage when shutting down
    await commands.delete(bot, config)
    await dispatcher.storage.close()
    if os.getenv("SUPPORT_WEBHOOK_ENABLED", "0") != "1":
        await bot.delete_webhook()
    await bot.session.close()


async def on_startup(
    apscheduler: AsyncIOScheduler,
    config: Config,
    bot: Bot,
    redis,
    dp,
) -> None:
    """
    Startup event handler. This runs when the bot starts up.

    :param apscheduler: AsyncIOScheduler: The apscheduler instance.
    :param config: Config: The config instance.
    :param bot: Bot: The bot instance.
    :param redis: The Redis client instance.
    """
    # Start apscheduler
    apscheduler.start()
    # Setup commands when starting up
    await commands.setup(bot, config)

    from app.db import tickets as ticket_db
    await ticket_db.init_db()

    # Activate PII filter and security middleware
    init_security(redis)

    # Activate anti-spam
    from .antispam import init_antispam
    init_antispam(redis)

    from app.jobs.sla import sla_alert_job, auto_close_job, offer_close_job
    apscheduler.add_job(
        sla_alert_job, trigger="interval", minutes=5,
        kwargs={"bot": bot, "config": config},
        id="support:sla_alert", replace_existing=True, max_instances=1,
        jobstore="memory",
    )
    apscheduler.add_job(
        auto_close_job, trigger="interval", minutes=15,
        kwargs={"bot": bot, "config": config},
        id="support:auto_close", replace_existing=True, max_instances=1,
        jobstore="memory",
    )

    # expose tickets API to admin panel
    import os
    os.environ["SUPPORT_GROUP_ID"] = str(config.bot.GROUP_ID)
    import uvicorn
    from app.api import app as fastapi_app
    api_port = int(os.getenv("SUPPORT_API_PORT", "8765"))
    api_cfg = uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=api_port, log_level="warning",
        access_log=False,
    )
    api_server = uvicorn.Server(api_cfg)
    task = asyncio.create_task(api_server.serve())
    # Store reference for graceful shutdown
    dp["_api_server"] = api_server
    dp["_api_task"] = task


async def main() -> None:
    """
    Main function that initializes the bot and starts the event loop.
    """
    # Load config
    config = load_config()

    # Initialize apscheduler
    job_store = RedisJobStore(
        host=config.redis.HOST,
        port=config.redis.PORT,
        db=config.redis.DB,
    )
    from apscheduler.jobstores.memory import MemoryJobStore
    apscheduler = AsyncIOScheduler(
        jobstores={
            "default": job_store,
            "memory": MemoryJobStore(),
        },
    )

    # Initialize Redis storage
    storage = RedisStorage.from_url(
        url=config.redis.dsn(),
    )

    # Create Bot and Dispatcher instances
    bot = Bot(
        token=config.bot.TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )
    dp = Dispatcher(
        apscheduler=apscheduler,
        storage=storage,
        config=config,
        bot=bot,
        redis=storage.redis,
    )

    # Register startup handler
    dp.startup.register(on_startup)
    # Register shutdown handler
    dp.shutdown.register(on_shutdown)

    # Include routes
    include_routers(dp)
    # Register middlewares
    register_middlewares(
        dp, config=config, redis=storage.redis, apscheduler=apscheduler
    )

    dp["dp"] = dp  # make dispatcher available in handlers

    # Check if webhook mode is enabled
    import os
    webhook_enabled = os.getenv("SUPPORT_WEBHOOK_ENABLED", "0") == "1"
    webhook_url = os.getenv("SUPPORT_WEBHOOK_URL", "")
    webhook_path = os.getenv("SUPPORT_WEBHOOK_PATH", "/telegram/webhook")

    if webhook_enabled and webhook_url:
        # Manually trigger startup (normally called by dp.start_polling)
        await on_startup(apscheduler=apscheduler, config=config, bot=bot, redis=storage.redis, dp=dp)

        # Set webhook on Telegram
        full_url = f"{webhook_url}{webhook_path}"
        await bot.set_webhook(
            url=full_url,
            allowed_updates=dp.resolve_used_update_types(),
        )
        log.info(f"Support bot webhook set: {full_url}")

        # Register webhook handler in the FastAPI app
        from app.api import set_webhook_handler
        set_webhook_handler(dp, bot)

        # Keep running (webhook receives updates via FastAPI)
        await asyncio.Event().wait()
    else:
        await bot.delete_webhook()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    # Set up logging
    setup_logger()
    # Run the bot
    asyncio.run(main())
