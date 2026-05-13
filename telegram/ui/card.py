"""
Карточка — единственное сообщение бота на пользователя.

Текстовые апдейты в рамках одного экрана меняют карточку через edit_message_text.
Когда меняется reply-клавиатура (переход между экранами), карточка пересоздаётся
как новое сообщение с reply_markup — это единственный надёжный способ установить
reply-клавиатуру у поля ввода: edit_message_text не умеет её менять.
"""
from __future__ import annotations

import logging
from typing import Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

logger = logging.getLogger(__name__)

ReplyKb = Union[ReplyKeyboardMarkup, ReplyKeyboardRemove]


async def render(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_kb: Optional[ReplyKb] = None,
    *,
    kb=None,  # legacy-параметр, игнорируется
) -> int:
    """Рендерит карточку.

    Если `reply_kb` задан — пересоздаёт карточку как новое сообщение с
    reply-клавиатурой у поля ввода (так как edit_message_text не умеет менять
    reply-клавиатуру). Иначе правит существующую карточку на месте.
    """
    data = await state.get_data()
    card_id: Optional[int] = data.get("card_id")

    if reply_kb is None:
        if card_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=card_id,
                    text=text,
                    reply_markup=None,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return card_id
            except TelegramBadRequest as e:
                low = str(e).lower()
                if "not modified" in low:
                    return card_id
                logger.info("Card %d unusable (%s), recreating", card_id, e)

        sent = await bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await state.update_data(card_id=sent.message_id)
        return sent.message_id

    # reply_kb is not None: нужно пересоздать карточку с новой клавиатурой.
    if card_id:
        await safe_delete(bot, chat_id, card_id)

    sent = await bot.send_message(
        chat_id,
        text,
        reply_markup=reply_kb,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    is_removal = isinstance(reply_kb, ReplyKeyboardRemove)
    await state.update_data(
        card_id=sent.message_id,
        reply_kb_active=not is_removal,
        reply_kb_cleared=is_removal,
    )
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


async def set_reply_kb(
    bot: Bot, chat_id: int, state: FSMContext, kb: ReplyKeyboardMarkup,
) -> None:
    """Алиас совместимости: переиспользует render с текстом текущей карточки.

    Используется редко (в основном — в обработчиках, которые делают
    render(text); set_reply_kb(kb) последовательно). Лучше передавать
    reply_kb прямо в render — это один запрос вместо двух.
    """
    data = await state.get_data()
    card_id = data.get("card_id")
    if not card_id:
        # Нет карточки — нечего обновлять; отправлять пустышку нельзя
        # (Telegram отклоняет message empty), так что просто помечаем флаг.
        await state.update_data(reply_kb_active=True)
        return
    # Удаляем старую карточку и шлём заглушку с новой клавиатурой.
    # Без текста send_message не работает, поэтому ставим один невидимый
    # символ; пользователь не успеет его прочесть, мы тут же удалим.
    try:
        sent = await bot.send_message(chat_id, "·", reply_markup=kb)
        await safe_delete(bot, chat_id, sent.message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    await state.update_data(reply_kb_active=True)


async def remove_reply_kb(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Снимает reply-клавиатуру. Идемпотентна по флагам."""
    data = await state.get_data()
    if not data.get("reply_kb_active") and data.get("reply_kb_cleared"):
        return
    try:
        sent = await bot.send_message(chat_id, "·", reply_markup=ReplyKeyboardRemove())
        await safe_delete(bot, chat_id, sent.message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    await state.update_data(reply_kb_active=False, reply_kb_cleared=True)


clear_reply_keyboard = remove_reply_kb
