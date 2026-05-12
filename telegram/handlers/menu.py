"""
Главное меню и помощь — всё в одной карточке.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram.keyboards.inline import help_kb, main_menu_kb, mode_kb
from telegram.ui import card, views

router = Router(name="menu")
logger = logging.getLogger(__name__)


async def show_main_menu(bot, chat_id: int, state: FSMContext) -> None:
    """Сбрасывает диалоговое FSM-состояние и рендерит главное меню в карточке."""
    await state.set_state(None)
    await card.clear_reply_keyboard(bot, chat_id, state)
    await card.render(bot, chat_id, state, views.WELCOME, kb=main_menu_kb())


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    # /start всегда возвращает в главное меню. Удаляем команду из чата, чтобы не мусорить.
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    logger.info("Start: user_id=%s", msg.from_user.id if msg.from_user else None)
    # Принудительно убиваем старую карточку: после «Очистить историю» в Telegram
    # она остаётся на сервере и edit_message_text проходит «успешно», но
    # пользователь правки не видит — и думает, что бот не запустился. Делаем
    # чистый send для свежей карточки.
    await card.delete(msg.bot, msg.chat.id, state)
    await show_main_menu(msg.bot, msg.chat.id, state)


@router.message(Command("help"))
async def cmd_help(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    # Тот же кейс: если карточка была после Clear History, edit может пройти
    # незаметно для пользователя. Пересоздаём свежую.
    await card.delete(msg.bot, msg.chat.id, state)
    await card.render(msg.bot, msg.chat.id, state, views.HELP, kb=help_kb())


@router.callback_query(F.data == "menu:trainer")
async def cb_trainer(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await card.render(cb.bot, cb.message.chat.id, state, views.MODE_SELECT, kb=mode_kb())


@router.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await card.render(cb.bot, cb.message.chat.id, state, views.HELP, kb=help_kb())


@router.callback_query(F.data == "nav:main")
async def cb_nav_main(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await show_main_menu(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "nav:mode")
async def cb_nav_mode(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await card.render(cb.bot, cb.message.chat.id, state, views.MODE_SELECT, kb=mode_kb())
