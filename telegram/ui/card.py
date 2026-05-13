"""
Тонкие обёртки над send_message и delete_message.

Бот общается в обычном чат-формате: каждый ответ — отдельное сообщение, без
редактирования предыдущих. `send` шлёт сообщение с HTML-разметкой и при
необходимости меняет reply-клавиатуру у поля ввода; `safe_delete` тихо
удаляет служебные сообщения (например, нажатия reply-кнопок).
"""
from __future__ import annotations

from typing import Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

ReplyKb = Union[ReplyKeyboardMarkup, ReplyKeyboardRemove]


async def send(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_kb: Optional[ReplyKb] = None,
) -> int:
    """Шлёт обычное сообщение в чат с HTML-разметкой.

    Если `reply_kb` задан, заодно обновляет reply-клавиатуру у поля ввода —
    она у бота единая на чат, любое сообщение с reply_markup её меняет.
    """
    sent = await bot.send_message(
        chat_id,
        text,
        reply_markup=reply_kb,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return sent.message_id


async def safe_delete(bot: Bot, chat_id: int, message_id: int) -> None:
    """Удалить сообщение, проглатывая ошибки (старое, нет прав, и т. п.)."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
