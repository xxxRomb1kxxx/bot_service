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
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

logger = logging.getLogger(__name__)


async def render(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    kb=None,
) -> int:
    """Рендерит карточку: правит существующее сообщение, иначе создаёт новое.

    Все управляющие кнопки — reply-клавиатура у поля ввода, поэтому само
    сообщение карточки никогда не имеет inline-клавиатуры (`kb` игнорируется,
    оставлен для совместимости со старыми вызовами).
    """
    data = await state.get_data()
    card_id: Optional[int] = data.get("card_id")

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
        reply_markup=None,
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


async def set_reply_kb(
    bot: Bot, chat_id: int, state: FSMContext, kb: ReplyKeyboardMarkup,
) -> None:
    """Устанавливает reply-клавиатуру у поля ввода.

    edit_message_text не умеет менять reply-клавиатуру (она привязана к чату,
    а не к сообщению), поэтому шлём transient-сообщение с нужной клавиатурой
    и тут же удаляем — сама клавиатура остаётся, пока не сменится новой
    или ReplyKeyboardRemove.
    """
    try:
        m = await bot.send_message(chat_id, "⁣", reply_markup=kb)
        await safe_delete(bot, chat_id, m.message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    await state.update_data(reply_kb_active=True)


async def remove_reply_kb(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Снимает reply-клавиатуру, если она установлена ботом.

    Идемпотентна: если флаг `reply_kb_active` уже выставлен False (или его нет
    при первом запуске), ничего не отправляет — избегаем лишнего флика
    transient-сообщения при каждом /start.
    """
    data = await state.get_data()
    if not data.get("reply_kb_active") and data.get("reply_kb_cleared"):
        return
    try:
        m = await bot.send_message(chat_id, "⁣", reply_markup=ReplyKeyboardRemove())
        await safe_delete(bot, chat_id, m.message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    await state.update_data(reply_kb_active=False, reply_kb_cleared=True)


# Алиас для обратной совместимости: старый код звал clear_reply_keyboard для
# одноразовой очистки залипшей клавиатуры от старой версии бота. Теперь это
# просто отдельный путь через remove_reply_kb.
clear_reply_keyboard = remove_reply_kb
