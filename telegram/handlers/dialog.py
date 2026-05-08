import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from dialog_engine.dialog_states import DialogState
from telegram.keyboards.inline import (
    BTN_DIAGNOSIS,
    BTN_FINISH_CONSULTATION,
    BTN_FINISH_DIALOG,
)
from telegram import api_client as api

router = Router(name="dialog")
logger = logging.getLogger(__name__)

# Параметры polling ответа пациента.
# POLL_TIMEOUT_SEC должен быть больше backend RESPONSE_TIMEOUT (обычно 60 с),
# чтобы бот не выходил из цикла раньше, чем LLM успеет ответить.
POLL_INTERVAL_SEC = 0.5
POLL_TIMEOUT_SEC = 75
POLL_MAX_ATTEMPTS = int(POLL_TIMEOUT_SEC / POLL_INTERVAL_SEC)

# Категории атрибутов для группировки в отчёте «Завершить консультацию»
_CATEGORY_TITLES = {
    "complaints": "📋 Жалобы",
    "anamnesis": "📖 Анамнез",
    "diagnostics": "🔬 Обследования",
}


@router.message(Command("finish"))
async def finish_dialog(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or (msg.from_user.id if msg.from_user else None)
    logger.info("Finish command: user_id=%s", tg_id)

    if session_id and tg_id:
        try:
            await api.delete_session(session_id, tg_id)
        except Exception as e:
            logger.warning("Could not delete session %s: %s", session_id, e)

    await state.clear()
    await msg.answer("✅ Диалог завершён.", reply_markup=ReplyKeyboardRemove())
    await msg.answer("Для нового кейса нажмите /start")


@router.message(Command("diagnosis"))
async def force_diagnosis(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    logger.info("Diagnosis command: user_id=%s", data.get("tg_id") or (msg.from_user.id if msg.from_user else None))
    if not data.get("session_id"):
        await msg.answer("Сначала начните кейс! Нажмите /start")
        return
    if data.get("mode") == "training":
        await msg.answer(
            "В тренировке постановка диагноза не используется — нажмите «✅ Завершить консультацию»."
        )
        return
    await state.set_state(DialogState.waiting_diagnosis)
    await msg.answer("📝 Поставьте диагноз — напишите его текстом:")


async def force_finish_consultation(msg: Message, state: FSMContext) -> None:
    """Тренировочный режим: завершить консультацию и получить отчёт."""
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or (msg.from_user.id if msg.from_user else None)
    logger.info("Finish consultation: user_id=%s", tg_id)

    if not session_id or not tg_id:
        await msg.answer("Сначала начните кейс! Нажмите /start", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    placeholder = await msg.answer("⏳ Анализирую консультацию…")

    try:
        result = await api.finish_consultation(session_id, tg_id)
    except api.BackendError as e:
        if e.status in (404, 409):
            await placeholder.edit_text(
                "Сессия уже завершена. Начните новый кейс через /start"
            )
            await state.clear()
            return
        logger.warning("finish-consultation backend error: %s %s", e.status, e.detail)
        await placeholder.edit_text("Произошла ошибка. Попробуйте ещё раз.")
        return

    text = _format_consultation_report(result)
    await placeholder.edit_text(text, parse_mode="HTML")
    await msg.answer(
        "Тренировка завершена. Для нового кейса нажмите /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()


def _format_consultation_report(result: dict) -> str:
    disease_name = result.get("disease_name", "?")
    coverage_pct = round(float(result.get("coverage", 0.0)) * 100)
    total_pct = round(float(result.get("total_score", 0.0)) * 100)
    lq = result.get("language_quality") or {}
    grade = int(lq.get("grade", 0) or 0)
    lq_comment = (lq.get("comment") or "").strip()
    lq_errors = lq.get("errors") or []
    attributes = result.get("attributes") or []

    grouped: dict[str, list[tuple[bool, str]]] = {"complaints": [], "anamnesis": [], "diagnostics": []}
    for a in attributes:
        cat = a.get("category", "")
        grouped.setdefault(cat, []).append((bool(a.get("collected")), str(a.get("label", ""))))

    lines: list[str] = []
    lines.append(f"📊 Отчёт по тренировке: <b>{disease_name}</b>")
    lines.append("")
    lines.append("<b>Атрибуты:</b>")
    for cat, items in grouped.items():
        if not items:
            continue
        lines.append(_CATEGORY_TITLES.get(cat, cat))
        for collected, label in items:
            icon = "✅" if collected else "❌"
            lines.append(f"  {icon} {label}")

    collected_count = sum(1 for a in attributes if a.get("collected"))
    total_count = len(attributes)
    lines.append("")
    lines.append(f"📈 Покрытие: {collected_count}/{total_count} ({coverage_pct}%)")

    lines.append("")
    grade_label = f"{grade}/5" if grade > 0 else "не оценено"
    lines.append(f"📝 Качество русского языка: {grade_label}")
    if lq_comment:
        lines.append(f"<i>{lq_comment}</i>")
    if lq_errors:
        lines.append("Замечания:")
        for err in lq_errors:
            lines.append(f"  • {err}")

    lines.append("")
    lines.append(f"🏆 Итоговый балл: <b>{total_pct}%</b>")
    return "\n".join(lines)


# ── Кнопки управления (reply keyboard) ────────────────────────────────────────
# Должны быть зарегистрированы ДО handle_dialog, иначе текст кнопки уйдёт пациенту.

@router.message(F.text == BTN_FINISH_DIALOG)
async def on_btn_finish_dialog(msg: Message, state: FSMContext) -> None:
    await finish_dialog(msg, state)


@router.message(F.text == BTN_DIAGNOSIS)
async def on_btn_diagnosis(msg: Message, state: FSMContext) -> None:
    await force_diagnosis(msg, state)


@router.message(F.text == BTN_FINISH_CONSULTATION)
async def on_btn_finish_consultation(msg: Message, state: FSMContext) -> None:
    await force_finish_consultation(msg, state)


@router.message(DialogState.waiting_question)
async def handle_dialog(msg: Message, state: FSMContext) -> None:
    user_id = msg.from_user.id if msg.from_user else None
    logger.info("Dialog message: user_id=%s, text=%r", user_id, msg.text)

    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or user_id

    if not session_id or not tg_id:
        await msg.answer("Произошла ошибка состояния. Начните новый кейс через /start")
        await state.clear()
        return

    placeholder = await msg.answer("⏳")

    try:
        queued = await api.send_message(session_id, msg.text or "", tg_id)
    except api.BackendError as e:
        if e.status == 409:
            await state.clear()
            await placeholder.edit_text("Сессия уже завершена. Начните новый кейс через /start")
        elif e.status == 404:
            await state.clear()
            await placeholder.edit_text("Сессия не найдена. Начните новый кейс через /start")
        elif e.status == 422:
            detail = e.detail
            if isinstance(detail, dict):
                user_msg = detail.get("message", "Пожалуйста, задавайте вопросы в рамках медицинского осмотра.")
            else:
                user_msg = "Пожалуйста, задавайте вопросы в рамках медицинского осмотра."
            await placeholder.edit_text(f"⚠️ {user_msg}")
        else:
            logger.warning("Backend error %s for user %s: %s", e.status, user_id, e.detail)
            await placeholder.edit_text("Произошла ошибка. Попробуйте повторить вопрос.")
        return

    message_id = queued.get("message_id")
    if not message_id:
        await placeholder.edit_text("Произошла ошибка. Попробуйте повторить вопрос.")
        return

    logger.info("Polling message %s for session %s", message_id, session_id)

    # Polling ответа пациента.
    # Sleep перенесён в конец итерации — первый запрос уходит сразу, без задержки.
    # Если задача была видна (status=processing) и вернулась 404 — бэкенд завершил
    # обработку и удалил запись; выходим в fallback немедленно.
    reply = None
    task_seen = False
    for attempt in range(POLL_MAX_ATTEMPTS):
        try:
            data = await api.get_message_result(session_id, message_id, tg_id)
            task_seen = True
            logger.info("Poll attempt %d: status=%s reply=%r", attempt + 1, data.get("status"), data.get("reply"))
        except api.BackendError as e:
            if e.status == 404:
                if task_seen:
                    logger.info("Task %s cleaned up after processing, falling back to session status", message_id)
                    break
                await asyncio.sleep(POLL_INTERVAL_SEC)
                continue
            logger.warning("Poll attempt %d error: status=%s detail=%s", attempt + 1, e.status, e.detail)
            await placeholder.edit_text("Произошла ошибка. Попробуйте повторить вопрос.")
            return

        # Баг #1: бэкенд сигнализирует об ошибке обработки через status=error
        if data.get("status") == "error":
            err = data.get("error") or "Не удалось обработать запрос"
            logger.warning("Async task failed: msg_id=%s err=%r", message_id, err)
            await placeholder.edit_text(f"⚠️ {err}")
            return

        if data.get("reply") is not None:
            logger.info("Got reply on attempt %d", attempt + 1)
            reply = data["reply"]
            break

        await asyncio.sleep(POLL_INTERVAL_SEC)

    # Fallback: задача исчезла до первого poll или была очищена после обработки
    if reply is None:
        try:
            status_data = await api.get_session_status(session_id, tg_id)
            logger.info("Session status fallback: %s", status_data)
            reply = (
                status_data.get("last_reply")
                or status_data.get("reply")
                or status_data.get("patient_reply")
            )
        except api.BackendError as e:
            logger.warning("Session status fallback error: %s %s", e.status, e.detail)

    if reply is None:
        await placeholder.edit_text("Пациент не ответил вовремя. Попробуйте ещё раз.")
        return
    await _send_reply(placeholder, msg, str(reply))


def _split_long(text: str, max_len: int) -> list[str]:
    """Разбивает текст на куски ≤ max_len, стараясь резать по абзацам или строкам."""
    chunks: list[str] = []
    while len(text) > max_len:
        cut = text.rfind("\n\n", 0, max_len)
        if cut < max_len // 2:
            cut = text.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


async def _send_reply(placeholder, msg: Message, text: str) -> None:
    """Отправляет ответ пациента. Если длиннее 4000 символов — бьёт на части,
    чтобы не словить TelegramBadRequest (лимит 4096 символов на сообщение).
    Reply-клавиатура управления уже закреплена внизу — её здесь не трогаем."""
    MAX = 4000
    if len(text) <= MAX:
        await placeholder.edit_text(text)
        return
    await placeholder.edit_text("📝 Ответ пациента:")
    for chunk in _split_long(text, MAX):
        await msg.answer(chunk)


@router.message(DialogState.waiting_diagnosis)
async def handle_diagnosis(msg: Message, state: FSMContext) -> None:
    user_id = msg.from_user.id if msg.from_user else None
    logger.info("Diagnosis message: user_id=%s, text=%r", user_id, msg.text)

    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or user_id

    if not session_id or not tg_id:
        await msg.answer("Произошла ошибка состояния. Начните новый кейс через /start")
        await state.clear()
        return

    placeholder = await msg.answer("⏳")

    try:
        result = await api.submit_diagnosis(session_id, msg.text or "", tg_id)
    except api.BackendError as e:
        if e.status == 422:
            detail = e.detail
            if isinstance(detail, dict):
                user_msg = detail.get("message", "Некорректный ввод. Попробуйте ещё раз.")
            else:
                user_msg = "Некорректный ввод. Попробуйте ещё раз."
            await placeholder.edit_text(f"⚠️ {user_msg}")
        else:
            logger.warning("Backend error %s for user %s: %s", e.status, user_id, e.detail)
            await placeholder.edit_text("Произошла ошибка при отправке диагноза. Попробуйте ещё раз.")
        return

    icon = "✅" if result["is_correct"] else "❌"
    score_pct = round(result["score"] * 100)

    await placeholder.edit_text(
        f"{icon} Результат: {result['message']}\n\n"
        f"Ваш диагноз: <i>{result['user_diagnosis']}</i>\n"
        f"Верный диагноз: {result['correct_diagnosis']}\n"
        f"Оценка: {score_pct}%",
        parse_mode="HTML",
    )

    card = result.get("card", {})
    lines = []
    if card.get("complaints"):
        lines.append("📋 Жалобы:\n" + "\n".join(f"• {c}" for c in card["complaints"]))
    if card.get("anamnesis"):
        lines.append("📖 Анамнез:\n" + "\n".join(f"• {a}" for a in card["anamnesis"]))
    if card.get("diagnostics"):
        lines.append("🔬 Обследования:\n" + "\n".join(f"• {d}" for d in card["diagnostics"]))
    if lines:
        await msg.answer("\n\n".join(lines), parse_mode="HTML")

    lq = result.get("language_quality") or {}
    grade = int(lq.get("grade", 0) or 0)
    if grade > 0 or lq.get("comment") or lq.get("errors"):
        lq_lines = [f"📝 Качество русского языка: {grade}/5" if grade > 0 else "📝 Качество русского языка: не оценено"]
        comment = (lq.get("comment") or "").strip()
        if comment:
            lq_lines.append(f"<i>{comment}</i>")
        errors = lq.get("errors") or []
        if errors:
            lq_lines.append("Замечания:")
            lq_lines.extend(f"  • {e}" for e in errors)
        await msg.answer("\n".join(lq_lines), parse_mode="HTML")

    await state.clear()
    await msg.answer(
        "Диалог завершён. Для нового кейса нажмите /start",
        reply_markup=ReplyKeyboardRemove(),
    )
