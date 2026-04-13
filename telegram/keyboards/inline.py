from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    """Выбор режима: Тренировка или Контрольный кейс."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Тренировка", callback_data="training")],
            [InlineKeyboardButton(text="🎯 Контрольный кейс", callback_data="control_case")],
        ]
    )


def training_menu() -> InlineKeyboardMarkup:
    """Выбор конкретной болезни для тренировки."""
    diseases = [
        ("🩸 Сахарный диабет", "diabetes"),
        ("💉 Анемия", "anemia"),
        ("🫁 Туберкулёз", "tuberculosis"),
        ("🔪 Аппендицит", "appendicitis"),
        ("⚡ Эпилепсия", "epilepsy"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"disease:{code}")]
            for name, code in diseases
        ]
    )


def dialog_control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🩺 Поставить диагноз", callback_data="cmd:diagnosis")],
            [InlineKeyboardButton(text="❌ Завершить диалог", callback_data="cmd:finish")],
        ]
    )


def get_main_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🏥 Тренажер")
    builder.button(text="ℹ️ Помощь")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


async def set_bot_commands(bot) -> None:
    commands = [
        BotCommand(command="start", description="🏥 Главное меню"),
        BotCommand(command="help", description="📖 Помощь и инструкции"),
        BotCommand(command="finish", description="⏹️ Завершить диалог"),
        BotCommand(command="diagnosis", description="🩺 Поставить диагноз"),
    ]
    await bot.set_my_commands(commands)