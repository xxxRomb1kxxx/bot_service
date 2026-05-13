"""
Диалог с пациентом, ввод диагноза и финальный отчёт.

Карточка показывает только текст беседы — управление вынесено в reply-клавиатуру
у поля ввода, чтобы кнопки были рядом с местом печати. Пользовательские
сообщения (вопросы пациенту и нажатия кнопок) удаляются после обработки.
"""
import asyncio
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from dialog_engine.dialog_states import DialogState
from telegram import api_client as api
from telegram.keyboards.inline import (
    BTN_ABORT,
    BTN_CANCEL_DIAGNOSIS,
    BTN_DIAGNOSIS,
    BTN_FINISH,
    BTN_REPORT_DONE,
    BTN_TAB_ATTRIBUTES,
    BTN_TAB_LANGUAGE,
    BTN_TAB_SUMMARY,
    back_to_menu_kb,
    diagnosis_result_kb,
    diagnosis_reply_kb,
    dialog_reply_kb,
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
    """Рендер карточки диалога — без inline-кнопок, управление в reply-клавиатуре."""
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

    await card.render(bot, chat_id, state, text)


async def _render_diagnosis_prompt(
    state: FSMContext, bot, chat_id: int, *, suffix: Optional[str] = None,
) -> None:
    """Рендер карточки ввода диагноза. Suffix добавляет ниже подсказки строку
    (например, статус «Проверяю…» или текст ошибки)."""
    data = await state.get_data()
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    if suffix:
        text = f"{text}\n\n{suffix}"
    await card.render(bot, chat_id, state, text)


async def _abort_session(bot, chat_id: int, state: FSMContext) -> None:
    """Снимает активную сессию на бэкенде и чистит FSM.

    Reply-клавиатуру не снимаем явно: следующий рендер карточки (главное меню
    или экран ошибки) пересоздаст карточку и переустановит нужную клавиатуру.
    """
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id")
    if session_id and tg_id:
        try:
            await api.delete_session(session_id, tg_id)
        except Exception as e:
            logger.warning("delete_session failed: %s", e)
    card_id = data.get("card_id")
    await state.set_state(None)
    await state.set_data({
        "card_id": card_id,
        "reply_kb_active": data.get("reply_kb_active", False),
        "reply_kb_cleared": data.get("reply_kb_cleared", False),
    })


# ── Reply-кнопки: завершение / прерывание / переход к диагнозу ────────────────
# Эти хендлеры регистрируются ДО общего handle_dialog, иначе текст кнопки уйдёт
# пациенту как вопрос.

@router.message(DialogState.waiting_question, F.text == BTN_FINISH)
async def on_btn_finish(msg: Message, state: FSMContext) -> None:
    """Тренировочный режим: завершить и получить отчёт."""
    await _delete_user_msg(msg)
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id")
    if not session_id or not tg_id:
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сессия потеряна."),
            reply_kb=back_to_menu_kb(),
        )
        return

    await _render_dialog(state, msg.bot, msg.chat.id, status="Анализирую консультацию…")

    try:
        result = await api.finish_consultation(session_id, tg_id)
    except api.BackendError as e:
        if e.status in (404, 409):
            await _abort_session(msg.bot, msg.chat.id, state)
            await card.render(
                msg.bot, msg.chat.id, state,
                views.error_card("Сессия уже завершена."),
                reply_kb=back_to_menu_kb(),
            )
            return
        if e.status in (502, 504):
            await _render_dialog(
                state, msg.bot, msg.chat.id,
                status="Сервер не успел подготовить отчёт. Подождите минуту и нажмите ещё раз.",
            )
            return
        logger.warning("finish-consultation error: %s %s", e.status, e.detail)
        await _render_dialog(
            state, msg.bot, msg.chat.id,
            status="Произошла ошибка. Попробуйте ещё раз.",
        )
        return

    # Переход в отчёт: вместо inline-вкладок используем reply-клавиатуру у поля ввода.
    await state.set_state(None)
    await state.update_data(report=result, session_id=None)
    await card.render(
        msg.bot, msg.chat.id, state,
        views.report_attributes_card(result),
        reply_kb=report_kb(),
    )


@router.message(DialogState.waiting_question, F.text == BTN_DIAGNOSIS)
async def on_btn_diagnosis(msg: Message, state: FSMContext) -> None:
    """Контрольный режим: переход к вводу диагноза."""
    await _delete_user_msg(msg)
    await state.set_state(DialogState.waiting_diagnosis)
    data = await state.get_data()
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.render(
        msg.bot, msg.chat.id, state, text, reply_kb=diagnosis_reply_kb(),
    )


@router.message(DialogState.waiting_diagnosis, F.text == BTN_CANCEL_DIAGNOSIS)
async def on_btn_cancel_diagnosis(msg: Message, state: FSMContext) -> None:
    """Из ввода диагноза обратно в диалог."""
    await _delete_user_msg(msg)
    await state.set_state(DialogState.waiting_question)
    data = await state.get_data()
    text = views.dialog_card(
        mode=data.get("mode", "training"),
        disease_name=data.get("disease_name", "?"),
        patient=data.get("patient") or {},
        last_question=data.get("last_question"),
        last_reply=data.get("last_reply"),
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.render(
        msg.bot, msg.chat.id, state, text,
        reply_kb=dialog_reply_kb(data.get("mode", "control")),
    )


@router.message(DialogState.waiting_question, F.text == BTN_ABORT)
@router.message(DialogState.waiting_diagnosis, F.text == BTN_ABORT)
async def on_btn_abort(msg: Message, state: FSMContext) -> None:
    """Прервать кейс из любого состояния."""
    await _delete_user_msg(msg)
    from telegram.handlers.menu import show_main_menu

    await _abort_session(msg.bot, msg.chat.id, state)
    await show_main_menu(msg.bot, msg.chat.id, state)


# ── Ввод вопроса (state=waiting_question, любой остальной текст) ──────────────

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
        await state.set_state(None)
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сессия потеряна. Начните новый кейс."),
            reply_kb=back_to_menu_kb(),
        )
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
        return  # _resolve_reply сам рендерит ошибку

    await state.update_data(
        last_reply=str(reply),
        q_count=int(data.get("q_count", 0) or 0) + 1,
    )
    await _render_dialog(state, msg.bot, msg.chat.id)


async def _handle_send_error(state, bot, chat_id, e: api.BackendError, user_id) -> None:
    if e.status in (404, 409):
        await _abort_session(bot, chat_id, state)
        await card.render(
            bot, chat_id, state,
            views.error_card("Сессия уже завершена или не найдена."),
            reply_kb=back_to_menu_kb(),
        )
        return
    if e.status == 422:
        detail = e.detail
        msg_text = (
            detail.get("message") if isinstance(detail, dict) else None
        ) or "Пожалуйста, задавайте вопросы в рамках медицинского осмотра."
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
    либо через polling GET /messages/{id}, либо через fallback /status."""
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


# ── Ввод диагноза (state=waiting_diagnosis, любой остальной текст) ────────────

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
        await state.set_state(None)
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сессия потеряна."),
            reply_kb=back_to_menu_kb(),
        )
        return

    await _render_diagnosis_prompt(
        state, msg.bot, msg.chat.id, suffix="⏳ <i>Проверяю диагноз…</i>",
    )

    try:
        result = await api.submit_diagnosis(session_id, text, tg_id)
    except api.BackendError as e:
        if e.status == 422:
            detail = e.detail
            user_msg = (detail.get("message") if isinstance(detail, dict) else None) \
                or "Некорректный ввод. Попробуйте ещё раз."
            await _render_diagnosis_prompt(
                state, msg.bot, msg.chat.id, suffix=f"⚠️ <i>{user_msg}</i>",
            )
            return
        if e.status in (502, 503, 504):
            await _render_diagnosis_prompt(
                state, msg.bot, msg.chat.id,
                suffix="⏳ <i>Сервер перегружен. Подождите минуту и отправьте ещё раз.</i>",
            )
            return
        logger.warning("submit_diagnosis error: %s %s", e.status, e.detail)
        await _abort_session(msg.bot, msg.chat.id, state)
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Не удалось отправить диагноз."),
            reply_kb=back_to_menu_kb(),
        )
        return

    # Готово: переход в карточку результата с reply-кнопкой «Готово».
    await state.set_state(None)
    await state.update_data(session_id=None, report=result)
    await card.render(
        msg.bot, msg.chat.id, state,
        views.diagnosis_result_card(result),
        reply_kb=diagnosis_result_kb(),
    )


# ── Вкладки отчёта (state=None, reply-клавиатура) ─────────────────────────────

async def _render_report_tab(msg: Message, state: FSMContext, renderer) -> None:
    data = await state.get_data()
    result = data.get("report") or {}
    await _delete_user_msg(msg)
    await card.render(msg.bot, msg.chat.id, state, renderer(result))


@router.message(StateFilter(None), F.text == BTN_TAB_ATTRIBUTES)
async def on_btn_tab_attributes(msg: Message, state: FSMContext) -> None:
    await _render_report_tab(msg, state, views.report_attributes_card)


@router.message(StateFilter(None), F.text == BTN_TAB_LANGUAGE)
async def on_btn_tab_language(msg: Message, state: FSMContext) -> None:
    await _render_report_tab(msg, state, views.report_language_card)


@router.message(StateFilter(None), F.text == BTN_TAB_SUMMARY)
async def on_btn_tab_summary(msg: Message, state: FSMContext) -> None:
    await _render_report_tab(msg, state, views.report_summary_card)


@router.message(StateFilter(None), F.text == BTN_REPORT_DONE)
async def on_btn_report_done(msg: Message, state: FSMContext) -> None:
    """«Готово» — удаляем карточку отчёта и показываем чистое главное меню."""
    from telegram.handlers.menu import show_main_menu

    await _delete_user_msg(msg)
    await card.delete(msg.bot, msg.chat.id, state)
    await state.set_state(None)
    data = await state.get_data()
    await state.set_data({
        "reply_kb_cleared": data.get("reply_kb_cleared", False),
        "reply_kb_active": data.get("reply_kb_active", False),
    })
    await show_main_menu(msg.bot, msg.chat.id, state)


# ── Команды совместимости (/finish, /diagnosis) ───────────────────────────────

@router.message(Command("finish"))
async def cmd_finish(msg: Message, state: FSMContext) -> None:
    """Алиас «прервать кейс»."""
    await _delete_user_msg(msg)
    from telegram.handlers.menu import show_main_menu

    await _abort_session(msg.bot, msg.chat.id, state)
    await show_main_menu(msg.bot, msg.chat.id, state)


@router.message(Command("diagnosis"))
async def cmd_diagnosis(msg: Message, state: FSMContext) -> None:
    """Алиас перехода к вводу диагноза (только контрольный режим)."""
    await _delete_user_msg(msg)
    data = await state.get_data()
    if not data.get("session_id"):
        await card.render(
            msg.bot, msg.chat.id, state,
            views.error_card("Сначала начните кейс через главное меню."),
            reply_kb=back_to_menu_kb(),
        )
        return
    if data.get("mode") == "training":
        await _render_dialog(
            state, msg.bot, msg.chat.id,
            status="В тренировке диагноз не вводится — используйте кнопку «Завершить и получить отчёт».",
        )
        return
    await state.set_state(DialogState.waiting_diagnosis)
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.render(
        msg.bot, msg.chat.id, state, text, reply_kb=diagnosis_reply_kb(),
    )


# ── Фолбэк: любой текст вне состояний удаляется, карточка не меняется ─────────

@router.message(F.text)
async def fallback_text(msg: Message, state: FSMContext) -> None:
    """Если пользователь пишет что-то вне диалога/диагноза — просто удаляем
    сообщение, чтобы чат оставался чистым."""
    await _delete_user_msg(msg)
