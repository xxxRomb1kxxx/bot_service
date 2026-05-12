"""
Диалог с пациентом, ввод диагноза и финальный отчёт — всё в одной карточке.

Пользовательские текстовые сообщения удаляются сразу после обработки, чтобы
чат не наполнялся историей. Контекст беседы хранится в FSM (последний обмен
и счётчик вопросов) и подсветка в карточке.
"""
import asyncio
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from dialog_engine.dialog_states import DialogState
from telegram import api_client as api
from telegram.keyboards.inline import (
    back_to_menu_kb,
    diagnosis_input_kb,
    diagnosis_result_kb,
    dialog_busy_kb,
    dialog_kb,
    report_kb,
)
from telegram.ui import card, views

router = Router(name="dialog")
logger = logging.getLogger(__name__)

# Polling: окно ожидания ответа пациента в асинхронном режиме API.
POLL_INTERVAL_SEC = 0.5
POLL_TIMEOUT_SEC = 75
POLL_MAX_ATTEMPTS = int(POLL_TIMEOUT_SEC / POLL_INTERVAL_SEC)


# ── Утилиты ───────────────────────────────────────────────────────────────────

async def _delete_user_msg(msg: Message) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)


async def _render_dialog(state: FSMContext, bot, chat_id: int, *, status: Optional[str] = None) -> None:
    data = await state.get_data()
    text = views.dialog_card(
        mode=data.get("mode", "training"),
        disease_name=data.get("disease_name", "?"),
        patient=data.get("patient") or {},
        last_question=data.get("last_question"),
        last_reply=data.get("last_reply"),
        q_count=int(data.get("q_count", 0) or 0),
        status=status,
    )
    kb = dialog_busy_kb() if status else dialog_kb(data.get("mode", "training"))
    await card.render(bot, chat_id, state, text, kb=kb)


async def _abort_session(bot, chat_id: int, state: FSMContext) -> None:
    """Снимает активную сессию на бэкенде и сбрасывает FSM."""
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id")
    if session_id and tg_id:
        try:
            await api.delete_session(session_id, tg_id)
        except Exception as e:
            logger.warning("delete_session failed: %s", e)
    # Сохраняем только card_id и флаг очищенной reply-клавиатуры, чтобы
    # дальше всё лилось в ту же карточку.
    card_id = data.get("card_id")
    reply_cleared = data.get("reply_kb_cleared", False)
    await state.set_state(None)
    await state.set_data({"card_id": card_id, "reply_kb_cleared": reply_cleared})


# ── Ввод вопроса (state=waiting_question) ─────────────────────────────────────

@router.message(DialogState.waiting_question)
async def handle_dialog(msg: Message, state: FSMContext) -> None:
    user_id = msg.from_user.id if msg.from_user else None
    text = (msg.text or "").strip()
    logger.info("Dialog message: user_id=%s, text=%r", user_id, text[:100])

    await _delete_user_msg(msg)
    if not text:
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or user_id
    if not session_id or not tg_id:
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сессия потеряна. Начните новый кейс."),
            kb=back_to_menu_kb(),
        )
        await state.set_state(None)
        return

    # Сразу показываем «обдумывает» с текущим вопросом, чтобы пользователь видел
    # прогресс и не нервничал во время LLM-вызова.
    await state.update_data(last_question=text)
    await _render_dialog(state, msg.bot, msg.chat.id, status="Пациент обдумывает ответ…")

    try:
        queued = await api.send_message(session_id, text, tg_id)
    except api.BackendError as e:
        await _handle_send_error(state, msg.bot, msg.chat.id, e, user_id)
        return

    reply = await _resolve_reply(queued, session_id, tg_id, state, msg.bot, msg.chat.id)
    if reply is None:
        # _resolve_reply сам рендерит ошибку в карточку
        return

    # Успешный ответ: обновляем историю и рендерим обычную карточку.
    await state.update_data(
        last_reply=str(reply),
        q_count=int(data.get("q_count", 0) or 0) + 1,
    )
    await _render_dialog(state, msg.bot, msg.chat.id)


async def _handle_send_error(state, bot, chat_id, e: api.BackendError, user_id) -> None:
    if e.status in (404, 409):
        await card.render(
            bot, chat_id, state,
            views.error_card("Сессия уже завершена или не найдена."),
            kb=back_to_menu_kb(),
        )
        await _abort_session(bot, chat_id, state)
        return
    if e.status == 422:
        detail = e.detail
        msg_text = (
            detail.get("message")
            if isinstance(detail, dict) else None
        ) or "Пожалуйста, задавайте вопросы в рамках медицинского осмотра."
        # Не считаем это «ошибкой» — просто подмешиваем подсказку в карточку диалога.
        await _render_dialog(state, bot, chat_id, status=f"⚠️ {msg_text}")
        return
    if e.status in (502, 503, 504):
        logger.warning("Transient backend error %s for user %s: %s", e.status, user_id, e.detail)
        await _render_dialog(
            state, bot, chat_id,
            status="Сервер сейчас перегружен — повторите вопрос через минуту.",
        )
        return
    logger.warning("Backend error %s for user %s: %s", e.status, user_id, e.detail)
    await _render_dialog(state, bot, chat_id, status="Произошла ошибка. Попробуйте повторить вопрос.")


async def _resolve_reply(queued: dict, session_id, tg_id, state, bot, chat_id) -> Optional[str]:
    """Достаёт ответ пациента: либо сразу из POST /message (синхронный режим),
    либо через polling GET /messages/{id} (асинхронный режим), либо через
    fallback /status. При окончательной неудаче рендерит карточку с ошибкой
    и возвращает None."""
    sync_reply = (
        queued.get("patient_reply")
        or queued.get("reply")
        or queued.get("last_reply")
    )
    if sync_reply is not None:
        return str(sync_reply)

    message_id = queued.get("message_id")
    if not message_id:
        logger.warning("send_message returned neither reply nor message_id: %r", queued)
        await _render_dialog(state, bot, chat_id, status="Произошла ошибка. Попробуйте повторить.")
        return None

    reply = None
    task_seen = False
    for attempt in range(POLL_MAX_ATTEMPTS):
        try:
            data = await api.get_message_result(session_id, message_id, tg_id)
            task_seen = True
        except api.BackendError as e:
            if e.status == 404:
                if task_seen:
                    break
                await asyncio.sleep(POLL_INTERVAL_SEC)
                continue
            if e.status in (502, 503, 504):
                await asyncio.sleep(POLL_INTERVAL_SEC)
                continue
            logger.warning("Poll error %s: %s", e.status, e.detail)
            await _render_dialog(state, bot, chat_id, status="Произошла ошибка. Попробуйте повторить.")
            return None

        if data.get("status") == "error":
            err = data.get("error") or "Не удалось обработать запрос"
            await _render_dialog(state, bot, chat_id, status=f"⚠️ {err}")
            return None
        if data.get("reply") is not None:
            reply = data["reply"]
            break
        await asyncio.sleep(POLL_INTERVAL_SEC)

    if reply is None:
        try:
            status_data = await api.get_session_status(session_id, tg_id)
            reply = (
                status_data.get("last_reply")
                or status_data.get("reply")
                or status_data.get("patient_reply")
            )
        except api.BackendError as e:
            logger.warning("Session status fallback error: %s %s", e.status, e.detail)

    if reply is None:
        await _render_dialog(state, bot, chat_id, status="Пациент не ответил вовремя. Попробуйте ещё раз.")
        return None
    return str(reply)


# ── Кнопки во время диалога ───────────────────────────────────────────────────

@router.callback_query(F.data == "dlg:finish")
async def cb_finish_consultation(cb: CallbackQuery, state: FSMContext) -> None:
    """Тренировочный режим: завершить и получить отчёт."""
    await cb.answer("Готовлю отчёт…")
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id")
    if not session_id or not tg_id:
        await card.render(
            cb.bot, cb.message.chat.id, state,
            views.error_card("Сессия потеряна."),
            kb=back_to_menu_kb(),
        )
        return

    await _render_dialog(state, cb.bot, cb.message.chat.id, status="Анализирую консультацию…")

    try:
        result = await api.finish_consultation(session_id, tg_id)
    except api.BackendError as e:
        if e.status in (404, 409):
            await card.render(
                cb.bot, cb.message.chat.id, state,
                views.error_card("Сессия уже завершена."),
                kb=back_to_menu_kb(),
            )
            await _abort_session(cb.bot, cb.message.chat.id, state)
            return
        if e.status in (502, 504):
            await _render_dialog(
                state, cb.bot, cb.message.chat.id,
                status="Сервер не успел подготовить отчёт. Подождите минуту и нажмите ещё раз.",
            )
            return
        logger.warning("finish-consultation error: %s %s", e.status, e.detail)
        await _render_dialog(
            state, cb.bot, cb.message.chat.id,
            status="Произошла ошибка. Попробуйте ещё раз.",
        )
        return

    # Кладём результат в FSM, чтобы вкладки отчёта могли перерендериваться без повторного запроса.
    await state.set_state(None)
    await state.update_data(report=result, session_id=None)
    await card.render(
        cb.bot, cb.message.chat.id, state,
        views.report_attributes_card(result),
        kb=report_kb("attributes"),
    )


@router.callback_query(F.data == "dlg:diagnosis")
async def cb_to_diagnosis(cb: CallbackQuery, state: FSMContext) -> None:
    """Контрольный режим: переход к вводу диагноза."""
    await cb.answer()
    data = await state.get_data()
    await state.set_state(DialogState.waiting_diagnosis)
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.render(cb.bot, cb.message.chat.id, state, text, kb=diagnosis_input_kb())


@router.callback_query(F.data == "dlg:cancel_diagnosis")
async def cb_cancel_diagnosis(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(DialogState.waiting_question)
    await _render_dialog(state, cb.bot, cb.message.chat.id)


@router.callback_query(F.data == "dlg:abort")
async def cb_abort(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer("Кейс прерван")
    from telegram.handlers.menu import show_main_menu

    await _abort_session(cb.bot, cb.message.chat.id, state)
    await show_main_menu(cb.bot, cb.message.chat.id, state)


# ── Ввод диагноза (state=waiting_diagnosis) ───────────────────────────────────

@router.message(DialogState.waiting_diagnosis)
async def handle_diagnosis(msg: Message, state: FSMContext) -> None:
    user_id = msg.from_user.id if msg.from_user else None
    text = (msg.text or "").strip()
    await _delete_user_msg(msg)
    if not text:
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or user_id
    if not session_id or not tg_id:
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сессия потеряна."),
            kb=back_to_menu_kb(),
        )
        await state.set_state(None)
        return

    # Показываем «отправляю диагноз…» в текущей карточке диагностики.
    prompt_text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    ) + "\n\n⏳ <i>Проверяю диагноз…</i>"
    await card.render(msg.bot, msg.chat.id, state, prompt_text, kb=dialog_busy_kb())

    try:
        result = await api.submit_diagnosis(session_id, text, tg_id)
    except api.BackendError as e:
        if e.status == 422:
            detail = e.detail
            user_msg = (detail.get("message") if isinstance(detail, dict) else None) \
                or "Некорректный ввод. Попробуйте ещё раз."
            await card.render(
                msg.bot, msg.chat.id, state,
                views.diagnosis_prompt_card(
                    patient=data.get("patient") or {},
                    q_count=int(data.get("q_count", 0) or 0),
                ) + f"\n\n⚠️ <i>{user_msg}</i>",
                kb=diagnosis_input_kb(),
            )
            return
        if e.status in (502, 503, 504):
            await card.render(
                msg.bot, msg.chat.id, state,
                views.diagnosis_prompt_card(
                    patient=data.get("patient") or {},
                    q_count=int(data.get("q_count", 0) or 0),
                ) + "\n\n⏳ <i>Сервер перегружен. Подождите минуту и отправьте ещё раз.</i>",
                kb=diagnosis_input_kb(),
            )
            return
        logger.warning("submit_diagnosis error: %s %s", e.status, e.detail)
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Не удалось отправить диагноз."),
            kb=back_to_menu_kb(),
        )
        await _abort_session(msg.bot, msg.chat.id, state)
        return

    # Готово: показываем карточку результата с кнопкой «Готово».
    await state.set_state(None)
    await state.update_data(session_id=None, report=result)
    await card.render(
        msg.bot, msg.chat.id, state,
        views.diagnosis_result_card(result),
        kb=diagnosis_result_kb(),
    )


# ── Вкладки отчёта ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("report:tab:"))
async def cb_report_tab(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    result = data.get("report") or {}
    tab = cb.data.split(":", 2)[2]
    if tab == "language":
        text = views.report_language_card(result)
    elif tab == "summary":
        text = views.report_summary_card(result)
    else:
        text = views.report_attributes_card(result)
    await card.render(cb.bot, cb.message.chat.id, state, text, kb=report_kb(tab))


@router.callback_query(F.data == "report:done")
async def cb_report_done(cb: CallbackQuery, state: FSMContext) -> None:
    """«Готово» — удаляем карточку отчёта и показываем чистое главное меню."""
    await cb.answer("Готово")
    from telegram.handlers.menu import show_main_menu

    # Удаляем старую карточку отчёта целиком, чтобы пользователь начал с чистого листа.
    await card.delete(cb.bot, cb.message.chat.id, state)
    await state.set_state(None)
    # Сохраняем только флаг очищенной reply-клавиатуры (от старой версии бота).
    data = await state.get_data()
    await state.set_data({"reply_kb_cleared": data.get("reply_kb_cleared", False)})
    await show_main_menu(cb.bot, cb.message.chat.id, state)


# ── Команды совместимости ─────────────────────────────────────────────────────
# Команды /finish и /diagnosis оставлены для обратной совместимости. Они теперь
# работают как кнопки «прервать» и «поставить диагноз» — просто эмулируем
# поведение и удаляем команду из чата.

@router.message(Command("finish"))
async def cmd_finish(msg: Message, state: FSMContext) -> None:
    await _delete_user_msg(msg)
    from telegram.handlers.menu import show_main_menu

    await _abort_session(msg.bot, msg.chat.id, state)
    await show_main_menu(msg.bot, msg.chat.id, state)


@router.message(Command("diagnosis"))
async def cmd_diagnosis(msg: Message, state: FSMContext) -> None:
    await _delete_user_msg(msg)
    data = await state.get_data()
    if not data.get("session_id"):
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сначала начните кейс через главное меню."),
            kb=back_to_menu_kb(),
        )
        return
    if data.get("mode") == "training":
        await _render_dialog(
            state, msg.bot, msg.chat.id,
            status="В тренировке диагноз не вводится — используйте «Завершить и получить отчёт».",
        )
        return
    await state.set_state(DialogState.waiting_diagnosis)
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.render(msg.bot, msg.chat.id, state, text, kb=diagnosis_input_kb())


# ── Фолбэк: любой текст вне состояний удаляется, карточка не меняется ─────────

@router.message(F.text)
async def fallback_text(msg: Message, state: FSMContext) -> None:
    """Если пользователь пишет что-то вне диалога/диагноза — просто удаляем
    сообщение, чтобы чат оставался чистым. Карточку не трогаем."""
    await _delete_user_msg(msg)
