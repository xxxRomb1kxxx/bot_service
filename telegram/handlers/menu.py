import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from telegram.keyboards.inline import get_main_kb, main_menu

router = Router(name="menu")
logger = logging.getLogger(__name__)

_WELCOME_TEXT = (
    "👨‍⚕️ СИМУЛЯТОР ДЛЯ ВРАЧЕЙ BFU\n\n"
    "🎯 Функционал бота:\n"
    "• 🏥 Тренировка — интерактивные кейсы с пациентами\n"
    "• 🤖 Реалистичный диалог — GigaChat имитирует пациента\n"
    "• 🩺 Проверка диагноза — автоматическая оценка правильности\n\n"
    "📋 Управление:\n"
    "• /finish — выйти из диалога в любой момент\n"
    "• /diagnosis — сразу перейти к постановке диагноза\n"
    "• /start — главное меню\n\n"
    "Выберите режим тренировки:"
)

_HELP_TEXT = (
    "📖 Как пользоваться симулятором:\n\n"
    "1️⃣ Начните — /start → «🏥 Тренажер»\n"
    "2️⃣ Выберите болезнь из списка\n"
    "3️⃣ Опрашивайте пациента (обычный текст)\n"
    "4️⃣ Завершите — /diagnosis или /finish\n"
    "5️⃣ Проверьте диагноз — напишите название болезни\n\n"
    "✅ Готово к тренировке!"
)


@router.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    await msg.answer(_WELCOME_TEXT, parse_mode="HTML", reply_markup=get_main_kb())


@router.callback_query(F.data == "start")
async def cb_start(cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.answer(_WELCOME_TEXT, parse_mode="HTML", reply_markup=main_menu())


@router.message(F.text == "🏥 Тренажер")
async def trainer_button(msg: Message) -> None:
    logger.info("Trainer button: user_id=%s", msg.from_user.id if msg.from_user else None)
    await msg.answer(
        "🩺 Выберите режим:",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@router.message(F.text == "ℹ️ Помощь")
@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(_HELP_TEXT, parse_mode="HTML")