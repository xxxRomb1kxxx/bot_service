import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from dialog_engine.dialog_states import DialogState
from telegram.keyboards.inline import dialog_control_keyboard
from telegram import api_client as api

router = Router(name="dialog")
logger = logging.getLogger(__name__)


@router.message(Command("finish"))
async def finish_dialog(msg: Message, state: FSMContext) -> None:
    logger.info("Finish command: user_id=%s", msg.from_user.id if msg.from_user else None)
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or (msg.from_user.id if msg.from_user else None)

    if session_id and tg_id:
        try:
            await api.delete_session(session_id, tg_id)
        except Exception as e:
            logger.warning("Could not delete session %s: %s", session_id, e)

    await state.clear()
    await msg.answer("✅ Диалог завершён.")
    await msg.answer("Для нового кейса нажмите /start")


@router.message(Command("diagnosis"))
async def force_diagnosis(msg: Message, state: FSMContext) -> None:
    logger.info("Diagnosis command: user_id=%s", msg.from_user.id if msg.from_user else None)
    data = await state.get_data()
    if not data.get("session_id"):
        await msg.answer("Сначала начните кейс! Нажмите /start")
        return
    await state.set_state(DialogState.waiting_diagnosis)
    await msg.answer("📝 Поставьте диагноз — напишите его текстом:")


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

    # Polling до появления reply (таймаут 60 сек, интервал 0.5 сек)
    # Бэкенд удаляет задачу атомарно с сохранением результата → нужен частый опрос
    reply = None
    for attempt in range(120):
        await asyncio.sleep(0.5)
        try:
            data = await api.get_message_result(session_id, message_id, tg_id)
        except api.BackendError as e:
            if e.status == 404:
                continue
            logger.warning("Poll attempt %d error: status=%s detail=%s", attempt + 1, e.status, e.detail)
            await placeholder.edit_text("Произошла ошибка. Попробуйте повторить вопрос.")
            return
        if data.get("reply") is not None:
            logger.info("Got reply on attempt %d", attempt + 1)
            reply = data["reply"]
            break

    if reply is None:
        await placeholder.edit_text("Пациент не ответил вовремя. Попробуйте ещё раз.")
        return
    await placeholder.edit_text(str(reply), reply_markup=dialog_control_keyboard())


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

    await state.clear()
    await msg.answer("Диалог завершён. Для нового кейса нажмите /start")
