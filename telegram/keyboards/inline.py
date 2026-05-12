"""
Inline-клавиатуры. Лейблы — глаголы первой формы, без эмодзи, по-Apple.
Активная вкладка отчёта помечается «•» в начале лейбла.
"""
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


# ── Болезни тренажёра ─────────────────────────────────────────────────────────
DISEASES: list[tuple[str, str]] = [
    ("Сахарный диабет", "diabetes"),
    ("Анемия", "anemia"),
    ("Туберкулёз", "tuberculosis"),
    ("Аппендицит", "appendicitis"),
    ("Эпилепсия", "epilepsy"),
]


# ── Главное меню ──────────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Тренажёр", callback_data="menu:trainer")],
        [InlineKeyboardButton(text="Помощь", callback_data="menu:help")],
    ])


def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="nav:main")],
    ])


# ── Выбор режима / болезни ────────────────────────────────────────────────────

def mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Тренировка", callback_data="mode:training")],
        [InlineKeyboardButton(text="Контрольный кейс", callback_data="mode:control")],
        [InlineKeyboardButton(text="Назад", callback_data="nav:main")],
    ])


def disease_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"disease:{code}")]
        for label, code in DISEASES
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="nav:mode")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Диалог ────────────────────────────────────────────────────────────────────

def dialog_kb(mode: str) -> InlineKeyboardMarkup:
    """Кнопки управления во время диалога с пациентом."""
    if mode == "training":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Завершить и получить отчёт", callback_data="dlg:finish")],
            [InlineKeyboardButton(text="Прервать", callback_data="dlg:abort")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поставить диагноз", callback_data="dlg:diagnosis")],
        [InlineKeyboardButton(text="Прервать", callback_data="dlg:abort")],
    ])


def diagnosis_input_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад к диалогу", callback_data="dlg:cancel_diagnosis")],
        [InlineKeyboardButton(text="Прервать", callback_data="dlg:abort")],
    ])


def dialog_busy_kb() -> InlineKeyboardMarkup:
    """Во время LLM-вызова доступна только «прервать»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Прервать", callback_data="dlg:abort")],
    ])


# ── Отчёт ─────────────────────────────────────────────────────────────────────

def report_kb(tab: str) -> InlineKeyboardMarkup:
    """Вкладки отчёта. Активная помечается «•»."""
    def mark(active: str, label: str) -> str:
        return f"•  {label}" if tab == active else label

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=mark("summary", "Итог"),
                                 callback_data="report:tab:summary"),
            InlineKeyboardButton(text=mark("attributes", "Атрибуты"),
                                 callback_data="report:tab:attributes"),
            InlineKeyboardButton(text=mark("language", "Язык"),
                                 callback_data="report:tab:language"),
        ],
        [InlineKeyboardButton(text="Готово", callback_data="report:done")],
    ])


def diagnosis_result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово", callback_data="report:done")],
    ])


# ── Ошибки / транзиент ────────────────────────────────────────────────────────

def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Главное меню", callback_data="nav:main")],
    ])


# ── Команды бота ──────────────────────────────────────────────────────────────

async def set_bot_commands(bot) -> None:
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)
