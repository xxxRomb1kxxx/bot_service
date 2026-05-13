"""
Главное меню и помощь — всё в одной карточке.
Управление вынесено в reply-клавиатуру у поля ввода.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from telegram.keyboards.inline import (
    BTN_BACK_MAIN,
    BTN_HELP_MAIN,
    BTN_TRAINER,
    help_kb,
    main_menu_kb,
    mode_kb,
)
from telegram.ui import card, views

router = Router(name="menu")
logger = logging.getLogger(__name__)


async def show_main_menu(bot, chat_id: int, state: FSMContext) -> None:
    """Сбрасывает диалоговое FSM-состояние и рендерит главное меню в карточке."""
    await state.set_state(None)
    await card.render(bot, chat_id, state, views.WELCOME)
    await card.set_reply_kb(bot, chat_id, state, main_menu_kb())


async def show_help(bot, chat_id: int, state: FSMContext) -> None:
    await card.render(bot, chat_id, state, views.HELP)
    await card.set_reply_kb(bot, chat_id, state, help_kb())


async def show_mode_select(bot, chat_id: int, state: FSMContext) -> None:
    await card.render(bot, chat_id, state, views.MODE_SELECT)
    await card.set_reply_kb(bot, chat_id, state, mode_kb())


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    # /start всегда возвращает в главное меню. Удаляем команду из чата, чтобы не мусорить.
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    logger.info("Start: user_id=%s", msg.from_user.id if msg.from_user else None)
    await show_main_menu(msg.bot, msg.chat.id, state)


@router.message(Command("help"))
async def cmd_help(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    await show_help(msg.bot, msg.chat.id, state)


@router.message(StateFilter(None), F.text == BTN_TRAINER)
async def on_btn_trainer(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    await show_mode_select(msg.bot, msg.chat.id, state)


@router.message(StateFilter(None), F.text == BTN_HELP_MAIN)
async def on_btn_help(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    await show_help(msg.bot, msg.chat.id, state)


@router.message(StateFilter(None), F.text == BTN_BACK_MAIN)
async def on_btn_back_main(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    await show_main_menu(msg.bot, msg.chat.id, state)