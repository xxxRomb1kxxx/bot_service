"""
HTML-шаблоны карточек в стиле Apple / Linear.

Принципы оформления:
- Типографическая иерархия: <b>заголовок</b>, заглавные «лейблы» секций,
  курсив для подсказок и мета-данных.
- Никаких ━━━ и эмодзи-перегруза. Один «акцент» (заголовок) и пробельный ритм.
- Числовые сводки рендерятся в <pre> с юникод-прогресс-барами █/░ —
  получается «карточка приборной панели», колонки выровнены.
- Эмодзи практически отсутствуют: их роль перенесена на типографику и порядок.
"""
from __future__ import annotations

from html import escape
from typing import Iterable, Optional

# Геометрия моноблока. Подобрано под комфортную ширину Telegram на смартфоне.
_LINE_WIDTH = 30
_LABEL_COL = 15
_BAR_LEN_BIG = 10
_BAR_LEN_SMALL = 4
_RULE = "─" * (_LINE_WIDTH - 2)


# ── Статические экраны ────────────────────────────────────────────────────────

WELCOME = (
    "<b>Симулятор для врачей BFU</b>\n"
    "Интерактивные кейсы с виртуальным пациентом.\n"
    "GigaChat имитирует поведение и реакции в реальном времени.\n"
    "\n"
    "ВОЗМОЖНОСТИ\n"
    "— Тренировка по конкретной болезни\n"
    "— Контрольный кейс со случайной болезнью\n"
    "— Оценка покрытия ключевых атрибутов\n"
    "— Анализ качества языка и стиля\n"
    "\n"
    "<i>Выберите действие ниже.</i>"
)

HELP = (
    "<b>Как пользоваться</b>\n"
    "\n"
    "1.  Откройте «Тренажёр» в главном меню.\n"
    "2.  Выберите режим:\n"
    "    — Тренировка — известная болезнь, в конце отчёт по покрытию.\n"
    "    — Контрольный кейс — случайная болезнь, в конце вы ставите диагноз.\n"
    "3.  Опрашивайте пациента в свободной форме.\n"
    "4.  Завершите консультацию — получите итоговый отчёт.\n"
    "\n"
    "<i>Совет: задавайте конкретные клинические вопросы — "
    "жалобы, анамнез, обследования.</i>"
)

MODE_SELECT = (
    "<b>Выбор режима</b>\n"
    "\n"
    "ТРЕНИРОВКА\n"
    "Известная болезнь. По завершении — отчёт о покрытии "
    "ключевых атрибутов и оценке речи.\n"
    "\n"
    "КОНТРОЛЬНЫЙ КЕЙС\n"
    "Случайная болезнь. По завершении самостоятельно ставите диагноз — "
    "бот его проверит и подсчитает балл."
)

DISEASE_SELECT = (
    "<b>Тренировка</b>\n"
    "\n"
    "Выберите болезнь для отработки."
)


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _bar(value: float, length: int) -> str:
    """Юникод-прогресс-бар. value clamp в [0, 1]."""
    v = max(0.0, min(1.0, float(value)))
    filled = round(v * length)
    return "█" * filled + "░" * (length - filled)


def _row_bar(label: str, value: float, suffix: str, bar_len: int = _BAR_LEN_BIG) -> str:
    """Строка моноблока: «Покрытие       ████░░░░░░  62%»."""
    return f"{label:<{_LABEL_COL}}{_bar(value, bar_len)}  {suffix}"


def _row_subbar(label: str, value: float, suffix: str) -> str:
    """Строка моноблока с короткой шкалой: число — справа по колонке _LINE_WIDTH."""
    body = f"{label:<{_LABEL_COL}}{_bar(value, _BAR_LEN_SMALL)}"
    pad = _LINE_WIDTH - len(body) - len(suffix)
    return f"{body}{' ' * max(1, pad)}{suffix}"


def _row_total(label: str, value: str) -> str:
    """Лейбл слева, число справа: «Итог                       44%»."""
    pad = _LINE_WIDTH - len(label) - len(value)
    pad = max(1, pad)
    return f"{label}{' ' * pad}{value}"


def _short_fio(fio: str) -> str:
    """«Соколова Мария Дмитриевна» → «Соколова М.Д.»."""
    if not fio:
        return ""
    parts = fio.strip().split()
    if len(parts) == 1:
        return parts[0]
    initials = "".join(f"{p[0]}." for p in parts[1:] if p)
    return f"{parts[0]} {initials}"


def patient_subtitle(patient: dict) -> str:
    """Подзаголовок: «Соколова М.Д., 40 лет · Бухгалтер»."""
    if not patient:
        return ""
    pieces: list[str] = []
    fio = patient.get("fio")
    if fio:
        short = _short_fio(str(fio))
        age = patient.get("age")
        if age:
            short = f"{short}, {age} лет"
        pieces.append(short)
    profession = patient.get("profession")
    if profession:
        pieces.append(str(profession))
    return " · ".join(pieces)


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _mode_label(mode: str) -> str:
    return "Тренировка" if mode == "training" else "Контрольный кейс"


# ── Диалог ────────────────────────────────────────────────────────────────────

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
    subtitle = patient_subtitle(patient)
    subtitle_full = f"{_mode_label(mode)} · {subtitle}" if subtitle else _mode_label(mode)

    lines: list[str] = [
        f"<b>{escape(disease_name)}</b>",
        escape(subtitle_full),
        "",
    ]

    if last_question is None and last_reply is None:
        lines.append("<i>Задайте первый вопрос пациенту — напишите его сообщением.</i>")
        lines.append("")
    else:
        if last_question is not None:
            lines.append("ВОПРОС")
            lines.append(escape(_truncate(last_question, 400)))
            lines.append("")
        if last_reply is not None:
            lines.append("ОТВЕТ")
            lines.append(escape(_truncate(last_reply, 1800)))
            lines.append("")

    if status:
        lines.append(f"<i>{escape(status)}</i>")
        lines.append("")

    # Безличная конструкция «вопросов задано: N» — не зависит от числа.
    lines.append(f"<i>вопросов задано: {q_count}</i>")
    return "\n".join(lines)


def diagnosis_prompt_card(*, patient: dict, q_count: int, hint: Optional[str] = None) -> str:
    subtitle = patient_subtitle(patient)
    lines: list[str] = [
        "<b>Постановка диагноза</b>",
    ]
    if subtitle:
        lines.append(escape(subtitle))
    lines.append("")
    lines.append(
        "<i>Напишите название болезни одной строкой. "
        "Бот сравнит ваш диагноз с правильным и оценит результат.</i>"
    )
    if hint:
        lines.append("")
        lines.append(f"<i>{escape(hint)}</i>")
    lines.append("")
    lines.append(f"<i>вопросов задано: {q_count}</i>")
    return "\n".join(lines)


# ── Отчёт ─────────────────────────────────────────────────────────────────────

def _attributes_breakdown(attributes: list[dict]) -> list[tuple[str, int, int]]:
    """Возвращает list[(category_label, collected, total)] в фикс. порядке."""
    titles = [
        ("complaints", "Жалобы"),
        ("anamnesis", "Анамнез"),
        ("diagnostics", "Обследования"),
    ]
    counts: dict[str, tuple[int, int]] = {}
    for cat, _ in titles:
        items = [a for a in attributes if a.get("category") == cat]
        counts[cat] = (sum(1 for a in items if a.get("collected")), len(items))
    return [(label, *counts[cat]) for cat, label in titles]


def report_summary_card(result: dict) -> str:
    disease = result.get("disease_name") or "—"
    attributes = result.get("attributes") or []
    collected = sum(1 for a in attributes if a.get("collected"))
    total = len(attributes)
    coverage = float(result.get("coverage", 0.0) or 0.0)
    total_score = float(result.get("total_score", 0.0) or 0.0)
    lq = result.get("language_quality") or {}
    grade = int(lq.get("grade", 0) or 0)

    coverage_pct = f"{round(coverage * 100)}%"
    total_pct = f"{round(total_score * 100)}%"

    pre_lines = [
        _row_bar("Покрытие", coverage, coverage_pct),
    ]
    if grade > 0:
        pre_lines.append(_row_bar("Язык", grade / 5, f"{grade}/5"))
    else:
        pre_lines.append(f"{'Язык':<{_LABEL_COL}}—  не оценено")
    pre_lines.append(_RULE)
    pre_lines.append(_row_total("Итог", total_pct))
    pre_lines.append("")
    pre_lines.append(_row_total("Атрибуты", f"{collected}/{total}"))
    for label, c, t in _attributes_breakdown(attributes):
        if t == 0:
            continue
        pre_lines.append(_row_subbar(label, (c / t) if t else 0, f"{c}/{t}"))

    pre_block = "<pre>" + escape("\n".join(pre_lines)) + "</pre>"

    return (
        f"<b>{escape(disease)}</b>\n"
        "Отчёт по тренировке\n"
        "\n"
        f"{pre_block}"
    )


def report_attributes_card(result: dict) -> str:
    """Tab «Атрибуты»: детальный список с галочками."""
    disease = result.get("disease_name") or "—"
    attributes = result.get("attributes") or []
    collected = sum(1 for a in attributes if a.get("collected"))
    total = len(attributes)

    titles = [
        ("complaints", "ЖАЛОБЫ"),
        ("anamnesis", "АНАМНЕЗ"),
        ("diagnostics", "ОБСЛЕДОВАНИЯ"),
    ]

    lines: list[str] = [
        "<b>Атрибуты</b>",
        f"{escape(disease)} · {collected} из {total}",
    ]
    for cat, title in titles:
        items = [a for a in attributes if a.get("category") == cat]
        if not items:
            continue
        lines.append("")
        lines.append(title)
        for a in items:
            mark = "✓" if a.get("collected") else "✗"
            lines.append(f"{mark}  {escape(str(a.get('label', '')))}")
    return "\n".join(lines)


def report_language_card(result: dict) -> str:
    """Tab «Язык»: оценка, комментарий, замечания."""
    lq = result.get("language_quality") or {}
    grade = int(lq.get("grade", 0) or 0)
    comment = (lq.get("comment") or "").strip()
    errors: Iterable[str] = lq.get("errors") or []

    lines: list[str] = ["<b>Язык и стиль</b>"]
    if grade > 0:
        lines.append(f"Оценка {grade}/5")
    else:
        lines.append("<i>не удалось оценить</i>")
    lines.append("")

    if comment and "не удалось" not in comment.lower():
        lines.append(f"<i>{escape(comment)}</i>")
        lines.append("")

    err_list = [str(e).strip() for e in errors if str(e).strip()]
    if err_list:
        lines.append("ЗАМЕЧАНИЯ")
        for e in err_list:
            lines.append(f"—  {escape(e)}")

    if grade == 0 and not err_list:
        lines.append(
            "<i>Языковой анализ временно недоступен. "
            "Попробуйте новый кейс позже.</i>"
        )
    return "\n".join(lines)


# ── Результат диагноза (контрольный кейс) ─────────────────────────────────────

def diagnosis_result_card(result: dict) -> str:
    is_correct = bool(result.get("is_correct"))
    user_dx = str(result.get("user_diagnosis") or "—")
    true_dx = str(result.get("correct_diagnosis") or "—")
    score = float(result.get("score", 0.0) or 0.0)
    score_pct = f"{round(score * 100)}%"
    msg = str(result.get("message") or "").strip()

    headline = "Диагноз поставлен корректно." if is_correct else "Диагноз неверный."

    pre_block = "<pre>" + escape(
        "\n".join([
            _row_bar("Точность", score, score_pct),
        ])
    ) + "</pre>"

    lines: list[str] = [
        f"<b>{escape(true_dx)}</b>",
        escape(headline),
        "",
        "ВАШ ДИАГНОЗ",
        escape(user_dx),
        "",
        "ВЕРНЫЙ ДИАГНОЗ",
        escape(true_dx),
        "",
        pre_block,
    ]
    if msg and msg.lower() not in headline.lower():
        lines.append("")
        lines.append(f"<i>{escape(msg)}</i>")
    return "\n".join(lines)


# ── Ошибка ────────────────────────────────────────────────────────────────────

def error_card(message: str, *, title: str = "Ошибка") -> str:
    return (
        f"<b>{escape(title)}</b>\n"
        "\n"
        f"{escape(message)}\n"
        "\n"
        "<i>Вернитесь в главное меню и попробуйте снова.</i>"
    )
