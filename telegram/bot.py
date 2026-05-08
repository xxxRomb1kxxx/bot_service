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
from telegram import api_client
from telegram.handlers.menu import router as menu_router
from telegram.handlers.dialog import router as dialog_router
from telegram.handlers.training import router as training_router
from telegram.handlers.admin import router as admin_router
from telegram.keyboards.inline import set_bot_commands
from aiogram.exceptions import TelegramConflictError

settings = get_settings()
setup_logging(settings.log_level)

BOT_TOKEN = settings.bot_token


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_router)
    dp.include_router(menu_router)
    dp.include_router(training_router)
    dp.include_router(dialog_router)

    await set_bot_commands(bot)

    logger = logging.getLogger(__name__)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted successfully.")

        logger.info("Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"]
        )

    finally:
        await bot.session.close()
        await api_client.close_session()