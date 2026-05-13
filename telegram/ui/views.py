"""
HTML-шаблоны карточек. Без эмодзи-перегруза: иконки маркируют только секции,
а основной текст в монохромном стиле «медицинского интерфейса».
"""
from __future__ import annotations

from html import escape
from typing import Iterable, Optional

# Горизонтальный разделитель внутри карточки.
HR = "━━━━━━━━━━━━━━━━━━━"

WELCOME = (
    "<b>👨‍⚕️ Симулятор для врачей</b>\n"
    f"{HR}\n\n"
    "Интерактивные кейсы с виртуальным пациентом.\n"
    "GigaChat имитирует поведение и реакции пациента в реальном времени.\n\n"
    "<b>Возможности:</b>\n"
    "• Тренировка по конкретной болезни\n"
    "• Контрольный кейс со случайной болезнью\n"
    "• Оценка покрытия ключевых атрибутов\n"
    "• Анализ качества языка и стиля общения\n\n"
    "<i>Выберите действие ниже.</i>"
)

HELP = (
    "<b>📖 Как пользоваться</b>\n"
    f"{HR}\n\n"
    "<b>1.</b> Откройте «🏥 Тренажёр» в главном меню.\n"
    "<b>2.</b> Выберите режим:\n"
    "    • <b>Тренировка</b> — известная болезнь, в конце отчёт по покрытию.\n"
    "    • <b>Контрольный кейс</b> — случайная болезнь, в конце нужно поставить диагноз.\n"
    "<b>3.</b> Опрашивайте пациента в свободной форме (текстом).\n"
    "<b>4.</b> Завершите консультацию — получите итоговый отчёт.\n\n"
    "<b>Совет:</b> <i>задавайте конкретные клинические вопросы — "
    "жалобы, анамнез, обследования.</i>"
)

MODE_SELECT = (
    "<b>🩺 Выбор режима</b>\n"
    f"{HR}\n\n"
    "<b>📚 Тренировка</b>\n"
    "<i>Известная болезнь. По завершении — отчёт о покрытии ключевых "
    "атрибутов и оценке речи.</i>\n\n"
    "<b>🎯 Контрольный кейс</b>\n"
    "<i>Случайная болезнь. По завершении самостоятельно ставите диагноз — "
    "бот проверит его и подсчитает балл.</i>"
)

DISEASE_SELECT = (
    "<b>🩺 Тренировка</b>\n"
    f"{HR}\n\n"
    "Выберите болезнь для отработки:"
)


def patient_header(patient: dict) -> str:
    """Шапка с инфо о пациенте, без переносов: ФИО • возраст • профессия."""
    if not patient:
        return "Пациент"
    parts = []
    fio = patient.get("fio")
    if fio:
        parts.append(str(fio))
    age = patient.get("age")
    if age:
        parts.append(f"{age} лет")
    profession = patient.get("profession")
    if profession:
        parts.append(str(profession))
    return " • ".join(parts) if parts else "Пациент"


def _mode_label(mode: str) -> str:
    return "Тренировка" if mode == "training" else "Контрольный кейс"


def _truncate(text: str, limit: int = 600) -> str:
    """Обрезает реплику, если она очень длинная, чтобы карточка не вылезла за 4096."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def dialog_intro_card(*, mode: str, disease_name: str, patient: dict, greeting: str) -> str:
    """Стартовое сообщение диалога: режим, инфо о пациенте и его приветствие."""
    return (
        f"<b>🩺 {escape(_mode_label(mode))} — {escape(disease_name)}</b>\n"
        f"{HR}\n"
        f"<i>{escape(patient_header(patient))}</i>\n\n"
        f"<b>👤 Пациент:</b>\n{escape(_truncate(greeting, 1800))}\n\n"
        f"<i>Опрашивайте пациента — пишите вопросы в чат.</i>"
    )


def patient_reply_card(reply: str) -> str:
    """Очередной ответ пациента — короткое сообщение в стиле обычного чата."""
    return f"<b>👤 Пациент:</b>\n{escape(_truncate(reply, 1800))}"


def status_card(text: str) -> str:
    """Короткое статус- или ошибочное сообщение."""
    return f"⚠️ <i>{escape(text)}</i>"


def dialog_card(
    *,
    mode: str,
    disease_name: str,
    patient: dict,
    last_question: Optional[str],
    last_reply: Optional[str],
    q_count: int,
    status: Optional[str] = None,
) -> str:
    """Карточка активного диалога.

    Показывает последний обмен (вопрос-ответ) и счётчик. Если есть `status` —
    показывает индикатор обработки внизу.
    """
    lines = [
        f"<b>{escape(_mode_label(mode))} — {escape(disease_name)}</b>",
        HR,
        f"<i>{escape(patient_header(patient))}</i>",
        HR,
        "",
    ]

    if last_question is None and last_reply is None:
        lines.append("<i>Задайте первый вопрос пациенту.</i>")
        lines.append("Напишите вопрос текстом — пациент ответит здесь же.")
    else:
        if last_question is not None:
            lines.append(f"<b>🩺 Вы спросили:</b>\n{escape(_truncate(last_question, 400))}")
            lines.append("")
        if last_reply is not None:
            lines.append(f"<b>👤 Пациент:</b>\n{escape(_truncate(last_reply, 1800))}")
            lines.append("")

    if status:
        lines.append(f"⏳ <i>{escape(status)}</i>")
        lines.append("")

    lines.append(HR)
    lines.append(f"<b>Задано вопросов:</b> {q_count}")
    return "\n".join(lines)


def diagnosis_prompt_card(*, patient: dict, q_count: int) -> str:
    return (
        "<b>🩺 Постановка диагноза</b>\n"
        f"{HR}\n"
        f"<i>{escape(patient_header(patient))}</i>\n"
        f"{HR}\n\n"
        "Напишите название болезни одной строкой.\n"
        "<i>Бот сравнит ваш диагноз с правильным и оценит результат.</i>\n\n"
        f"<b>Вопросов задано:</b> {q_count}"
    )


def _format_attributes_section(attributes: list[dict]) -> list[str]:
    titles = {
        "complaints": "📋 Жалобы",
        "anamnesis": "📖 Анамнез",
        "diagnostics": "🔬 Обследования",
    }
    grouped: dict[str, list[tuple[bool, str]]] = {
        "complaints": [], "anamnesis": [], "diagnostics": [],
    }
    for a in attributes:
        cat = a.get("category", "")
        grouped.setdefault(cat, []).append(
            (bool(a.get("collected")), str(a.get("label", "")))
        )

    out: list[str] = []
    for cat, items in grouped.items():
        if not items:
            continue
        out.append(f"<b>{titles.get(cat, cat)}</b>")
        for collected, label in items:
            icon = "✅" if collected else "❌"
            out.append(f"  {icon} {escape(label)}")
        out.append("")
    return out


def report_attributes_card(result: dict) -> str:
    attributes = result.get("attributes") or []
    collected = sum(1 for a in attributes if a.get("collected"))
    total = len(attributes)
    coverage_pct = round(float(result.get("coverage", 0.0)) * 100)
    disease = result.get("disease_name", "?")

    lines = [
        f"<b>📊 Отчёт — {escape(disease)}</b>",
        HR,
        "<b>Вкладка:</b> Атрибуты",
        HR,
        "",
    ]
    lines.extend(_format_attributes_section(attributes))
    lines.append(HR)
    lines.append(f"<b>📈 Покрытие:</b> {collected}/{total} ({coverage_pct}%)")
    return "\n".join(lines)


def report_language_card(result: dict) -> str:
    lq = result.get("language_quality") or {}
    grade = int(lq.get("grade", 0) or 0)
    comment = (lq.get("comment") or "").strip()
    errors: Iterable[str] = lq.get("errors") or []
    disease = result.get("disease_name", "?")

    lines = [
        f"<b>📊 Отчёт — {escape(disease)}</b>",
        HR,
        "<b>Вкладка:</b> Язык и стиль",
        HR,
        "",
    ]
    if grade > 0:
        lines.append(f"<b>📝 Оценка качества языка:</b> {grade}/5")
    else:
        lines.append("<b>📝 Оценка качества языка:</b> <i>не удалось оценить</i>")
    if comment and "не удалось" not in comment.lower():
        lines.append("")
        lines.append(f"<i>{escape(comment)}</i>")
    err_list = [str(e).strip() for e in errors if str(e).strip()]
    if err_list:
        lines.append("")
        lines.append("<b>Замечания:</b>")
        for e in err_list:
            lines.append(f"  • {escape(e)}")
    if grade == 0 and not err_list:
        lines.append("")
        lines.append(
            "<i>Языковой анализ временно недоступен. "
            "Попробуйте новый кейс позже.</i>"
        )
    return "\n".join(lines)


def report_summary_card(result: dict, diagnosis: Optional[dict] = None) -> str:
    coverage_pct = round(float(result.get("coverage", 0.0)) * 100)
    total_pct = round(float(result.get("total_score", 0.0)) * 100)
    lq_grade = int((result.get("language_quality") or {}).get("grade", 0) or 0)
    disease = result.get("disease_name", "?")

    lines = [
        f"<b>📊 Отчёт — {escape(disease)}</b>",
        HR,
        "<b>Вкладка:</b> Итог",
        HR,
        "",
    ]
    if diagnosis:
        is_correct = bool(diagnosis.get("is_correct"))
        dx_icon = "✅" if is_correct else "❌"
        dx_pct = round(float(diagnosis.get("score", 0.0)) * 100)
        lines.append(f"<b>🎯 Диагноз:</b> {dx_icon} {dx_pct}%")
    lines.append(f"<b>📈 Покрытие атрибутов:</b> {coverage_pct}%")
    if lq_grade > 0:
        lines.append(f"<b>📝 Качество языка:</b> {lq_grade}/5")
    else:
        lines.append("<b>📝 Качество языка:</b> <i>не оценено</i>")
    lines.append("")
    lines.append(HR)
    lines.append(f"<b>🏆 Итоговый балл:</b> <b>{total_pct}%</b>")
    return "\n".join(lines)


def diagnosis_result_card(result: dict) -> str:
    is_correct = bool(result.get("is_correct"))
    icon = "✅" if is_correct else "❌"
    verdict = "Верно" if is_correct else "Неверно"
    user_dx = str(result.get("user_diagnosis", "—"))
    true_dx = str(result.get("correct_diagnosis", "—"))
    score_pct = round(float(result.get("score", 0.0)) * 100)

    # Бэкенд в `message` уже шлёт всю ту же инфу строкой — её не показываем,
    # чтобы избежать дублирования с структурированными полями ниже.
    lines = [
        f"<b>{icon} Результат диагноза — {verdict}</b>",
        HR,
        f"<b>Ваш диагноз:</b> {escape(user_dx)}",
        f"<b>Верный диагноз:</b> {escape(true_dx)}",
        "",
        HR,
        f"<b>🏆 Оценка:</b> {score_pct}%",
    ]
    return "\n".join(lines)


def error_card(message: str, *, title: str = "Ошибка") -> str:
    return (
        f"<b>⚠️ {escape(title)}</b>\n"
        f"{HR}\n\n"
        f"{escape(message)}\n\n"
        "<i>Вернитесь в главное меню и попробуйте снова.</i>"
    )
