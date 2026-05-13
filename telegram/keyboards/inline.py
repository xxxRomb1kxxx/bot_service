"""
Клавиатуры бота — все управление вынесено в reply-клавиатуры у поля ввода.

Кнопки сидят прямо у поля ввода, где врач печатает текст. Нажатие отправляет
текст кнопки, который ловит хендлер по F.text == BTN_* и удаляет сообщение.
"""
from aiogram.types import BotCommand, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


# ── Тексты reply-кнопок (используются для матчинга в хендлерах) ───────────────

# Главное меню / помощь
BTN_TRAINER = "🏥 Тренажёр"
BTN_HELP_MAIN = "📖 Помощь"
BTN_BACK_MAIN = "◀️ В главное меню"

# Выбор режима / болезни
BTN_MODE_TRAINING = "📚 Тренировка"
BTN_MODE_CONTROL = "🎯 Контрольный кейс"
BTN_BACK_MODE = "◀️ К выбору режима"

# Диалог / диагноз
BTN_FINISH = "✅ Завершить и получить отчёт"
BTN_ABORT = "❌ Прервать кейс"
BTN_DIAGNOSIS = "🩺 Поставить диагноз"
BTN_CANCEL_DIAGNOSIS = "◀️ Вернуться к диалогу"

# Отчёт по тренировке
BTN_TAB_ATTRIBUTES = "📋 Атрибуты"
BTN_TAB_LANGUAGE = "📝 Язык"
BTN_TAB_SUMMARY = "🏆 Итог"
BTN_REPORT_DONE = "✅ Готово"


# ── Болезни тренажёра (icon, label, code) ─────────────────────────────────────
DISEASES: list[tuple[str, str, str]] = [
    ("🩸", "Сахарный диабет", "diabetes"),
    ("💉", "Анемия", "anemia"),
    ("🫁", "Туберкулёз", "tuberculosis"),
    ("🔪", "Аппендицит", "appendicitis"),
    ("⚡", "Эпилепсия", "epilepsy"),
]

# Маппинг текста кнопки болезни → код. Используется в хендлере для разбора нажатия.
DISEASE_LABEL_TO_CODE: dict[str, str] = {
    f"{icon} {label}": code for icon, label, code in DISEASES
}


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    """Собирает reply-клавиатуру из списка рядов кнопок."""
    builder = ReplyKeyboardBuilder()
    sizes: list[int] = []
    for row in rows:
        for text in row:
            builder.button(text=text)
        sizes.append(len(row))
    builder.adjust(*sizes)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


# ── Главное меню ──────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    return _kb([BTN_TRAINER], [BTN_HELP_MAIN])


def help_kb() -> ReplyKeyboardMarkup:
    return _kb([BTN_BACK_MAIN])


# ── Выбор режима / болезни ────────────────────────────────────────────────────

def mode_kb() -> ReplyKeyboardMarkup:
    return _kb([BTN_MODE_TRAINING], [BTN_MODE_CONTROL], [BTN_BACK_MAIN])


def disease_kb() -> ReplyKeyboardMarkup:
    rows = [[f"{icon} {label}"] for icon, label, _ in DISEASES]
    rows.append([BTN_BACK_MODE])
    return _kb(*rows)


# ── Reply-клавиатуры для диалога и диагноза ───────────────────────────────────

def dialog_reply_kb(mode: str) -> ReplyKeyboardMarkup:
    """Reply-клавиатура во время диалога с пациентом."""
    primary = BTN_FINISH if mode == "training" else BTN_DIAGNOSIS
    return _kb([primary], [BTN_ABORT])


def diagnosis_reply_kb() -> ReplyKeyboardMarkup:
    """Reply-клавиатура при вводе диагноза (контрольный режим)."""
    return _kb([BTN_CANCEL_DIAGNOSIS], [BTN_ABORT])


# ── Отчёт по тренировке ───────────────────────────────────────────────────────

def report_kb() -> ReplyKeyboardMarkup:
    """Вкладки отчёта: атрибуты / язык / итог + «готово»."""
    return _kb(
        [BTN_TAB_ATTRIBUTES, BTN_TAB_LANGUAGE, BTN_TAB_SUMMARY],
        [BTN_REPORT_DONE],
    )


def diagnosis_result_kb() -> ReplyKeyboardMarkup:
    return _kb([BTN_REPORT_DONE])


# ── Ошибки / транзиент ────────────────────────────────────────────────────────

def back_to_menu_kb() -> ReplyKeyboardMarkup:
    return _kb([BTN_BACK_MAIN])


# ── Команды бота ──────────────────────────────────────────────────────────────

async def set_bot_commands(bot) -> None:
    commands = [
        BotCommand(command="start", description="🏥 Главное меню"),
        BotCommand(command="help", description="📖 Помощь"),
    ]
    await bot.set_my_commands(commands)