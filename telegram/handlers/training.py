"""
Старт кейса (тренировка / контрольный) — переход к экрану диалога.
Все шаги рендерятся в одну карточку.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from dialog_engine.dialog_states import DialogState
from telegram import api_client as api
from telegram.keyboards.inline import (
    back_to_menu_kb,
    dialog_kb,
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


async def _enter_dialog(
    cb: CallbackQuery,
    state: FSMContext,
    *,
    case: dict,
    mode: str,
) -> None:
    """Сохраняет данные сессии в FSM и рендерит карточку диалога."""
    tg_id = cb.from_user.id
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
    await card.render(cb.bot, cb.message.chat.id, state, text, kb=dialog_kb(mode))


# ── Выбор болезни ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "mode:training")
async def cb_mode_training(cb: CallbackQuery, state: FSMContext) -> None:
    logger.info("Mode=training: user_id=%s", cb.from_user.id if cb.from_user else None)
    await cb.answer()
    await card.render(
        cb.bot, cb.message.chat.id, state, views.DISEASE_SELECT, kb=disease_kb(),
    )


@router.callback_query(F.data.startswith("disease:"))
async def cb_disease(cb: CallbackQuery, state: FSMContext) -> None:
    disease_code = cb.data.split(":", 1)[1]
    tg_id = cb.from_user.id
    logger.info("Start training: user_id=%s disease=%s", tg_id, disease_code)
    await cb.answer("Создаю кейс…")

    try:
        await api.ensure_whitelisted(tg_id)
        case = await _start_case_with_retry(tg_id, disease_type=disease_code, mode="training")
    except api.BackendError as e:
        await card.render(
            cb.bot, cb.message.chat.id, state,
            views.error_card(str(e.detail)),
            kb=back_to_menu_kb(),
        )
        return

    await _enter_dialog(cb, state, case=case, mode="training")


# ── Контрольный кейс ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "mode:control")
async def cb_mode_control(cb: CallbackQuery, state: FSMContext) -> None:
    tg_id = cb.from_user.id
    logger.info("Start control: user_id=%s", tg_id)
    await cb.answer("Создаю кейс…")

    try:
        await api.ensure_whitelisted(tg_id)
        case = await _start_random_case_with_retry(tg_id, mode="control")
    except api.BackendError as e:
        await card.render(
            cb.bot, cb.message.chat.id, state,
            views.error_card(str(e.detail)),
            kb=back_to_menu_kb(),
        )
        return

    await _enter_dialog(cb, state, case=case, mode="control")
