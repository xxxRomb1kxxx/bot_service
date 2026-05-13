"""
Диалог с пациентом, ввод диагноза и финальный отчёт — в обычном чате.

Каждый ответ бота — новое сообщение. Сообщения пользователя не удаляются
(кроме нажатий reply-кнопок, чтобы не было дубликатов одинаковых меток).
Reply-клавиатура у поля ввода переключается по мере смены экранов.
"""
import asyncio
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from dialog_engine.dialog_states import DialogState
from telegram import api_client as api
from telegram.keyboards.inline import (
    BTN_ABORT,
    BTN_CANCEL_DIAGNOSIS,
    BTN_DIAGNOSIS,
    BTN_FINISH,
    BTN_REPORT_DONE,
    BTN_TAB_ATTRIBUTES,
    BTN_TAB_DIAGNOSIS,
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

POLL_INTERVAL_SEC = 0.5
POLL_TIMEOUT_SEC = 75
POLL_MAX_ATTEMPTS = int(POLL_TIMEOUT_SEC / POLL_INTERVAL_SEC)


# ── Утилиты ───────────────────────────────────────────────────────────────────

async def _delete_button_press(msg: Message) -> None:
    """Удаляет нажатие reply-кнопки — её текст-метка повторяется при каждом
    нажатии и захламляет чат."""
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)


async def _abort_session(bot, chat_id: int, state: FSMContext) -> None:
    """Снимает активную сессию на бэкенде и чистит FSM."""
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id")
    if session_id and tg_id:
        try:
            await api.delete_session(session_id, tg_id)
        except Exception as e:
            logger.warning("delete_session failed: %s", e)
    await state.set_state(None)
    await state.set_data({})


# ── Reply-кнопки: завершение / прерывание / переход к диагнозу ────────────────

@router.message(DialogState.waiting_question, F.text == BTN_FINISH)
async def on_btn_finish(msg: Message, state: FSMContext) -> None:
    """Тренировочный режим: завершить и получить отчёт."""
    await _delete_button_press(msg)
    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id")
    if not session_id or not tg_id:
        await card.send(
            msg.bot, msg.chat.id,
            views.error_card("Сессия потеряна."),
            reply_kb=back_to_menu_kb(),
        )
        return

    try:
        async with ChatActionSender.typing(bot=msg.bot, chat_id=msg.chat.id):
            result = await api.finish_consultation(session_id, tg_id)
    except api.BackendError as e:
        if e.status in (404, 409):
            await _abort_session(msg.bot, msg.chat.id, state)
            await card.send(
                msg.bot, msg.chat.id,
                views.error_card("Сессия уже завершена."),
                reply_kb=back_to_menu_kb(),
            )
            return
        if e.status in (502, 504):
            await card.send(
                msg.bot, msg.chat.id,
                views.status_card("Сервер не успел подготовить отчёт. Подождите минуту и нажмите ещё раз."),
            )
            return
        logger.warning("finish-consultation error: %s %s", e.status, e.detail)
        await card.send(
            msg.bot, msg.chat.id,
            views.status_card("Произошла ошибка. Попробуйте ещё раз."),
        )
        return

    await state.set_state(None)
    await state.update_data(report=result, session_id=None)
    await card.send(
        msg.bot, msg.chat.id,
        views.report_attributes_card(result),
        reply_kb=report_kb(),
    )


@router.message(DialogState.waiting_question, F.text == BTN_DIAGNOSIS)
async def on_btn_diagnosis(msg: Message, state: FSMContext) -> None:
    """Контрольный режим: переход к вводу диагноза."""
    await _delete_button_press(msg)
    await state.set_state(DialogState.waiting_diagnosis)
    data = await state.get_data()
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.send(msg.bot, msg.chat.id, text, reply_kb=diagnosis_reply_kb())


@router.message(DialogState.waiting_diagnosis, F.text == BTN_CANCEL_DIAGNOSIS)
async def on_btn_cancel_diagnosis(msg: Message, state: FSMContext) -> None:
    """Из ввода диагноза обратно к опросу пациента."""
    await _delete_button_press(msg)
    await state.set_state(DialogState.waiting_question)
    data = await state.get_data()
    await card.send(
        msg.bot, msg.chat.id,
        "<i>Возвращаемся к диалогу. Задавайте вопросы пациенту.</i>",
        reply_kb=dialog_reply_kb(data.get("mode", "control")),
    )


@router.message(DialogState.waiting_question, F.text == BTN_ABORT)
@router.message(DialogState.waiting_diagnosis, F.text == BTN_ABORT)
async def on_btn_abort(msg: Message, state: FSMContext) -> None:
    """Прервать кейс из любого состояния."""
    await _delete_button_press(msg)
    from telegram.handlers.menu import show_main_menu

    await _abort_session(msg.bot, msg.chat.id, state)
    await show_main_menu(msg.bot, msg.chat.id, state)


# ── Ввод вопроса (state=waiting_question, любой остальной текст) ──────────────

@router.message(DialogState.waiting_question)
async def handle_dialog(msg: Message, state: FSMContext) -> None:
    user_id = msg.from_user.id if msg.from_user else None
    text = (msg.text or "").strip()
    if not text:
        return
    logger.info("Dialog message: user_id=%s, text=%r", user_id, text[:100])

    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or user_id
    if not session_id or not tg_id:
        await state.set_state(None)
        await card.send(
            msg.bot, msg.chat.id,
            views.error_card("Сессия потеряна. Начните новый кейс."),
            reply_kb=back_to_menu_kb(),
        )
        return

    try:
        async with ChatActionSender.typing(bot=msg.bot, chat_id=msg.chat.id):
            queued = await api.send_message(session_id, text, tg_id)
            reply = await _resolve_reply(queued, session_id, tg_id, msg.bot, msg.chat.id)
    except api.BackendError as e:
        await _handle_send_error(msg.bot, msg.chat.id, state, e, user_id)
        return

    if reply is None:
        return  # _resolve_reply сам отправил ошибку

    await state.update_data(
        q_count=int(data.get("q_count", 0) or 0) + 1,
    )
    await card.send(msg.bot, msg.chat.id, views.patient_reply_card(reply))


async def _handle_send_error(bot, chat_id, state, e: api.BackendError, user_id) -> None:
    if e.status in (404, 409):
        await _abort_session(bot, chat_id, state)
        await card.send(
            bot, chat_id,
            views.error_card("Сессия уже завершена или не найдена."),
            reply_kb=back_to_menu_kb(),
        )
        return
    if e.status == 422:
        detail = e.detail
        msg_text = (
            detail.get("message") if isinstance(detail, dict) else None
        ) or "Пожалуйста, задавайте вопросы в рамках медицинского осмотра."
        await card.send(bot, chat_id, views.status_card(msg_text))
        return
    if e.status in (502, 503, 504):
        logger.warning("Transient backend error %s for user %s: %s", e.status, user_id, e.detail)
        await card.send(
            bot, chat_id,
            views.status_card("Сервер сейчас перегружен — повторите вопрос через минуту."),
        )
        return
    logger.warning("Backend error %s for user %s: %s", e.status, user_id, e.detail)
    await card.send(bot, chat_id, views.status_card("Произошла ошибка. Попробуйте повторить вопрос."))


async def _resolve_reply(
    queued: dict, session_id, tg_id, bot, chat_id,
) -> Optional[str]:
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
        await card.send(bot, chat_id, views.status_card("Произошла ошибка. Попробуйте повторить."))
        return None

    reply = None
    task_seen = False
    for _ in range(POLL_MAX_ATTEMPTS):
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
            await card.send(bot, chat_id, views.status_card("Произошла ошибка. Попробуйте повторить."))
            return None

        if data.get("status") == "error":
            err = data.get("error") or "Не удалось обработать запрос"
            await card.send(bot, chat_id, views.status_card(err))
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
        await card.send(
            bot, chat_id,
            views.status_card("Пациент не ответил вовремя. Попробуйте ещё раз."),
        )
        return None
    return str(reply)


# ── Ввод диагноза (state=waiting_diagnosis, любой остальной текст) ────────────

@router.message(DialogState.waiting_diagnosis)
async def handle_diagnosis(msg: Message, state: FSMContext) -> None:
    user_id = msg.from_user.id if msg.from_user else None
    text = (msg.text or "").strip()
    if not text:
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    tg_id = data.get("tg_id") or user_id
    if not session_id or not tg_id:
        await state.set_state(None)
        await card.send(
            msg.bot, msg.chat.id,
            views.error_card("Сессия потеряна."),
            reply_kb=back_to_menu_kb(),
        )
        return

    try:
        async with ChatActionSender.typing(bot=msg.bot, chat_id=msg.chat.id):
            diagnosis = await api.submit_diagnosis(session_id, text, tg_id)
            # Сразу подтягиваем полный отчёт (атрибуты + язык + итог), чтобы
            # в контрольном режиме показывать те же вкладки, что в тренировке.
            report = await _fetch_report_after_diagnosis(session_id, tg_id)
    except api.BackendError as e:
        if e.status == 422:
            detail = e.detail
            user_text = (detail.get("message") if isinstance(detail, dict) else None) \
                or "Некорректный ввод. Попробуйте ещё раз."
            await card.send(msg.bot, msg.chat.id, views.status_card(user_text))
            return
        if e.status in (502, 503, 504):
            await card.send(
                msg.bot, msg.chat.id,
                views.status_card("Сервер перегружен. Подождите минуту и отправьте ещё раз."),
            )
            return
        logger.warning("submit_diagnosis error: %s %s", e.status, e.detail)
        await _abort_session(msg.bot, msg.chat.id, state)
        await card.send(
            msg.bot, msg.chat.id,
            views.error_card("Не удалось отправить диагноз."),
            reply_kb=back_to_menu_kb(),
        )
        return

    await state.set_state(None)
    await state.update_data(session_id=None, diagnosis=diagnosis, report=report or {})
    await card.send(
        msg.bot, msg.chat.id,
        views.diagnosis_result_card(diagnosis),
        reply_kb=report_kb(include_diagnosis=True) if report else diagnosis_result_kb(),
    )


async def _fetch_report_after_diagnosis(session_id: str, tg_id: int) -> Optional[dict]:
    """Подтягивает полный отчёт после успешной отправки диагноза.

    Если бэкенд уже считает сессию завершённой (404/409) или временно недоступен,
    возвращаем None — пользователь увидит только результат по диагнозу.
    """
    try:
        return await api.finish_consultation(session_id, tg_id)
    except api.BackendError as e:
        if e.status in (404, 409, 502, 503, 504):
            logger.info("Report unavailable after diagnosis (%s): %s", e.status, e.detail)
            return None
        raise


# ── Вкладки отчёта (state=None, reply-клавиатура persistент) ──────────────────
# Reply-клавиатура отчёта уже установлена при первом показе, и сохраняется на
# чат-уровне, поэтому здесь только шлём новое сообщение с содержимым вкладки.

async def _send_report_tab(msg: Message, state: FSMContext, renderer) -> None:
    await _delete_button_press(msg)
    data = await state.get_data()
    result = data.get("report") or {}
    await card.send(msg.bot, msg.chat.id, renderer(result))


@router.message(StateFilter(None), F.text == BTN_TAB_DIAGNOSIS)
async def on_btn_tab_diagnosis(msg: Message, state: FSMContext) -> None:
    await _delete_button_press(msg)
    data = await state.get_data()
    diagnosis = data.get("diagnosis") or {}
    await card.send(msg.bot, msg.chat.id, views.diagnosis_result_card(diagnosis))


@router.message(StateFilter(None), F.text == BTN_TAB_ATTRIBUTES)
async def on_btn_tab_attributes(msg: Message, state: FSMContext) -> None:
    await _send_report_tab(msg, state, views.report_attributes_card)


@router.message(StateFilter(None), F.text == BTN_TAB_LANGUAGE)
async def on_btn_tab_language(msg: Message, state: FSMContext) -> None:
    await _send_report_tab(msg, state, views.report_language_card)


@router.message(StateFilter(None), F.text == BTN_TAB_SUMMARY)
async def on_btn_tab_summary(msg: Message, state: FSMContext) -> None:
    await _delete_button_press(msg)
    data = await state.get_data()
    result = data.get("report") or {}
    diagnosis = data.get("diagnosis")  # None в тренировочном режиме
    await card.send(msg.bot, msg.chat.id, views.report_summary_card(result, diagnosis))


@router.message(StateFilter(None), F.text == BTN_REPORT_DONE)
async def on_btn_report_done(msg: Message, state: FSMContext) -> None:
    """«Готово» — возвращаемся в главное меню."""
    from telegram.handlers.menu import show_main_menu

    await _delete_button_press(msg)
    await state.set_state(None)
    await state.set_data({})
    await show_main_menu(msg.bot, msg.chat.id, state)


# ── Команды совместимости (/finish, /diagnosis) ───────────────────────────────

@router.message(Command("finish"))
async def cmd_finish(msg: Message, state: FSMContext) -> None:
    """Алиас «прервать кейс»."""
    from telegram.handlers.menu import show_main_menu

    await _abort_session(msg.bot, msg.chat.id, state)
    await show_main_menu(msg.bot, msg.chat.id, state)


@router.message(Command("diagnosis"))
async def cmd_diagnosis(msg: Message, state: FSMContext) -> None:
    """Алиас перехода к вводу диагноза (только контрольный режим)."""
    data = await state.get_data()
    if not data.get("session_id"):
        await card.send(
            msg.bot, msg.chat.id,
            views.error_card("Сначала начните кейс через главное меню."),
            reply_kb=back_to_menu_kb(),
        )
        return
    if data.get("mode") == "training":
        await card.send(
            msg.bot, msg.chat.id,
            views.status_card("В тренировке диагноз не вводится — нажмите «Завершить и получить отчёт»."),
        )
        return
    await state.set_state(DialogState.waiting_diagnosis)
    text = views.diagnosis_prompt_card(
        patient=data.get("patient") or {},
        q_count=int(data.get("q_count", 0) or 0),
    )
    await card.send(msg.bot, msg.chat.id, text, reply_kb=diagnosis_reply_kb())
