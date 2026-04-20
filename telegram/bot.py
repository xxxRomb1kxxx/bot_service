"""
Запуск из корня проекта: python -m telegram.bot
"""
import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import get_settings, setup_logging
from telegram.handlers.menu import router as menu_router
from telegram.handlers.dialog import router as dialog_router
from telegram.handlers.training import router as training_router
from telegram.handlers.admin import router as admin_router
from telegram.keyboards.inline import set_bot_commands

settings = get_settings()
setup_logging(settings.log_level)

BOT_TOKEN = settings.bot_token


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Порядок важен: admin и training раньше dialog,
    # чтобы команды /wl_* и callback'и не проваливались в fallback
    dp.include_router(admin_router)
    dp.include_router(menu_router)
    dp.include_router(training_router)
    dp.include_router(dialog_router)

    await set_bot_commands(bot)
    logger = logging.getLogger(__name__)

    # Попытка удалить webhook с обработкой исключений
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted successfully.")
    except Exception as e:
        logger.warning(f"Не удалось удалить webhook: {e}")

    # Запуск polling с retry на случай TelegramConflictError
    while True:
        try:
            logger.info("Starting polling...")
            await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
        except Exception as e:
            logger.error(f"Polling failed: {e}")
            logger.info("Повторная попытка через 3 секунды...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Удаляем lock при завершении
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)