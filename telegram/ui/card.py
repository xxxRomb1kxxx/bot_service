"""
Карточка — единственное редактируемое сообщение бота на пользователя.

Все служебные экраны (главное меню, выбор режима/болезни, диалог, отчёт)
рендерятся в одно и то же сообщение через edit_message_text. Когда состояние
сбрасывается (например, /start после завершения отчёта), карточка удаляется
вместе с прочим мусором, и история чата остаётся пустой.
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardRemove

logger = logging.getLogger(__name__)


async def render(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    kb: Optional[InlineKeyboardMarkup] = None,
) -> int:
    """Рендерит карточку: правит существующее сообщение, иначе создаёт новое.

    Возвращает message_id карточки. При edit-not-modified / edit-not-found /
    permissions silently отступаем к созданию нового сообщения.
    """
    data = await state.get_data()
    card_id: Optional[int] = data.get("card_id")

    if card_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=card_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return card_id
        except TelegramBadRequest as e:
            low = str(e).lower()
            if "not modified" in low:
                # Текст идентичен — попробуем хотя бы обновить клавиатуру.
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id, message_id=card_id, reply_markup=kb,
                    )
                except TelegramBadRequest:
                    pass
                return card_id
            logger.info("Card %d unusable (%s), recreating", card_id, e)

    sent = await bot.send_message(
        chat_id,
        text,
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await state.update_data(card_id=sent.message_id)
    return sent.message_id


async def delete(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Удаляет карточку и стирает её id из FSM."""
    data = await state.get_data()
    card_id = data.get("card_id")
    if not card_id:
        return
    await state.update_data(card_id=None)
    await safe_delete(bot, chat_id, card_id)


async def safe_delete(bot: Bot, chat_id: int, message_id: int) -> None:
    """Удалить сообщение, проглатывая ошибки (старое сообщение, нет прав, etc.)."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


async def clear_reply_keyboard(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Снимает залипший reply-keyboard от старой версии бота. Запускается один раз
    на пользователя; результат запоминается в FSM, чтобы не плодить шум."""
    data = await state.get_data()
    if data.get("reply_kb_cleared"):
        return
    try:
        m = await bot.send_message(chat_id, "⁣", reply_markup=ReplyKeyboardRemove())
        await safe_delete(bot, chat_id, m.message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    await state.update_data(reply_kb_cleared=True)
