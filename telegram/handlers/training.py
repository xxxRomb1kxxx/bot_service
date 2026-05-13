"""
Старт кейса (тренировка / контрольный) — переход к экрану диалога.
Все шаги рендерятся в одну карточку, управление — в reply-клавиатуре.
"""
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from dialog_engine.dialog_states import DialogState
from telegram import api_client as api
from telegram.keyboards.inline import (
    BTN_BACK_MODE,
    BTN_MODE_CONTROL,
    BTN_MODE_TRAINING,
    DISEASE_LABEL_TO_CODE,
    back_to_menu_kb,
    dialog_reply_kb,
    disease_kb,
)
from telegram.ui import card, views

router = Router(name="training")
logger = logging.getLogger(__name__)


async def _cleanup_stuck_session(tg_id: int) -> None:
    """Удаляет зависшую сессию пользователя через вайтлист."""
    entry = await api.get_whitelist_user(f"tg_{tg_id}", tg_id)
    session_id = entry.get("session_id")
    if session_id:
        await api.delete_session(session_id, tg_id)
        logger.info("Cleaned up stuck session %s for user %s", session_id, tg_id)


async def _start_case_with_retry(
    tg_id: int, disease_type: str | None = None, mode: str = "control",
) -> dict:
    """Запускает кейс; при 409 чистит зависшую сессию и повторяет один раз."""
    try:
        return await api.start_case(tg_id, disease_type=disease_type, mode=mode)
    except api.BackendError as e:
        if e.status != 409:
            raise
        await _cleanup_stuck_session(tg_id)
        return await api.start_case(tg_id, disease_type=disease_type, mode=mode)


async def _start_random_case_with_retry(tg_id: int, mode: str = "control") -> dict:
    try:
        return await api.start_random_case(tg_id, mode=mode)
    except api.BackendError as e:
        if e.status != 409:
            raise
        await _cleanup_stuck_session(tg_id)
        return await api.start_random_case(tg_id, mode=mode)


async def _show_disease_select(msg: Message, state: FSMContext) -> None:
    await card.render(
        msg.bot, msg.chat.id, state, views.DISEASE_SELECT, reply_kb=disease_kb(),
    )


async def _show_mode_select(msg: Message, state: FSMContext) -> None:
    # Локальный импорт, чтобы не плодить циклов между menu.py и training.py.
    from telegram.handlers.menu import show_mode_select

    await show_mode_select(msg.bot, msg.chat.id, state)


async def _enter_dialog(
    msg: Message,
    state: FSMContext,
    *,
    case: dict,
    mode: str,
) -> None:
    """Сохраняет данные сессии в FSM и рендерит карточку диалога."""
    tg_id = msg.from_user.id
    patient = case.get("patient") or {}
    disease_name = case.get("disease_type") or "?"
    greeting = case.get("greeting") or "Добрый день, доктор. Можно войти на приём?"

    await state.update_data(
        session_id=case["session_id"],
        tg_id=tg_id,
        mode=mode,
        disease_name=disease_name,
        patient=patient,
        q_count=0,
        last_question=None,
        last_reply=greeting,
    )
    await state.set_state(DialogState.waiting_question)

    text = views.dialog_card(
        mode=mode,
        disease_name=disease_name,
        patient=patient,
        last_question=None,
        last_reply=greeting,
        q_count=0,
    )
    await card.render(
        msg.bot, msg.chat.id, state, text, reply_kb=dialog_reply_kb(mode),
    )


# ── Выбор режима ──────────────────────────────────────────────────────────────

@router.message(StateFilter(None), F.text == BTN_MODE_TRAINING)
async def on_btn_mode_training(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    logger.info("Mode=training: user_id=%s", msg.from_user.id if msg.from_user else None)
    await _show_disease_select(msg, state)


@router.message(StateFilter(None), F.text == BTN_BACK_MODE)
async def on_btn_back_mode(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    await _show_mode_select(msg, state)


@router.message(StateFilter(None), F.text.in_(DISEASE_LABEL_TO_CODE.keys()))
async def on_btn_disease(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    disease_code = DISEASE_LABEL_TO_CODE[msg.text]
    tg_id = msg.from_user.id
    logger.info("Start training: user_id=%s disease=%s", tg_id, disease_code)

    try:
        await api.ensure_whitelisted(tg_id)
        case = await _start_case_with_retry(tg_id, disease_type=disease_code, mode="training")
    except api.BackendError as e:
        await card.render(
            msg.bot, msg.chat.id, state, views.error_card(str(e.detail)),
            reply_kb=back_to_menu_kb(),
        )
        return

    await _enter_dialog(msg, state, case=case, mode="training")


# ── Контрольный кейс ──────────────────────────────────────────────────────────

@router.message(StateFilter(None), F.text == BTN_MODE_CONTROL)
async def on_btn_mode_control(msg: Message, state: FSMContext) -> None:
    await card.safe_delete(msg.bot, msg.chat.id, msg.message_id)
    tg_id = msg.from_user.id
    logger.info("Start control: user_id=%s", tg_id)

    try:
        await api.ensure_whitelisted(tg_id)
        case = await _start_random_case_with_retry(tg_id, mode="control")
    except api.BackendError as e:
        await card.render(
            msg.bot, msg.chat.id, state, views.error_card(str(e.detail)),
            reply_kb=back_to_menu_kb(),
        )
        return

    await _enter_dialog(msg, state, case=case, mode="control")