import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from dialog_engine.dialog_states import DialogState
from telegram.handlers.dialog import finish_dialog, force_diagnosis
from telegram.keyboards.inline import training_menu
from telegram import api_client as api

router = Router(name="training")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "training")
async def training(cb: CallbackQuery) -> None:
    logger.info("Training menu: user_id=%s", cb.from_user.id if cb.from_user else None)
    await cb.answer()
    await cb.message.answer(
        "🩺 Выберите заболевание для отработки:",
        reply_markup=training_menu(),
    )


@router.callback_query(F.data.in_({"cmd:diagnosis", "cmd:finish"}))
async def dialog_commands(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    if cb.data == "cmd:diagnosis":
        await force_diagnosis(cb.message, state)
    elif cb.data == "cmd:finish":
        await finish_dialog(cb.message, state)


@router.callback_query(F.data == "control_case")
async def control_case(cb: CallbackQuery, state: FSMContext) -> None:
    logger.info("Control case: user_id=%s", cb.from_user.id if cb.from_user else None)
    await cb.answer()
    tg_id = cb.from_user.id

    try:
        await api.ensure_whitelisted(tg_id)
        case = await api.start_random_case(tg_id)
    except api.BackendError as e:
        await cb.message.answer(f"⚠️ {e.detail}")
        return

    await state.update_data(session_id=case["session_id"], tg_id=tg_id)
    await state.set_state(DialogState.waiting_question)

    patient = case["patient"]
    # await cb.message.answer(
    #     f"🎯 Контрольный кейс начат!\n\n"
    #     f"👤 Пациент: {patient['fio']}\n"
    #     f"Пол: {patient['gender']} | Возраст: {patient['age']} лет\n"
    #     f"Профессия: {patient['profession']}\n\n"
    #     "Болезнь скрыта — поставьте диагноз самостоятельно.",
    #     parse_mode="HTML",
    # )
    await cb.message.answer(case.get("greeting", "Добрый день, доктор. Можно войти на приём?"))


@router.callback_query(F.data.startswith("disease:"))
async def start_case(cb: CallbackQuery, state: FSMContext) -> None:
    user_id = cb.from_user.id if cb.from_user else None
    logger.info("Disease case: user_id=%s, data=%s", user_id, cb.data)
    await cb.answer()

    disease_code = cb.data.split(":", 1)[1]
    tg_id = cb.from_user.id

    try:
        await api.ensure_whitelisted(tg_id)
        case = await api.start_case(tg_id, disease_type=disease_code)
    except api.BackendError as e:
        if e.status == 409:
            await cb.message.answer(
                "⚠️ У вас уже есть активная сессия.\n"
                "Завершите её командой /finish, затем начните новую."
            )
        else:
            await cb.message.answer(f"⚠️ {e.detail}")
        return

    await state.update_data(session_id=case["session_id"], tg_id=tg_id)
    await state.set_state(DialogState.waiting_question)

    patient = case["patient"]
    disease_name = case.get("disease_type") or "неизвестно"

    logger.info("Case started: disease=%s, user_id=%s", disease_code, user_id)
    # await cb.message.answer(
    #     f"✅ Кейс начат!\n\n"
    #     f"🦠 Болезнь: {disease_name}\n\n"
    #     f"👤 Пациент: {patient['fio']}\n"
    #     f"Пол: {patient['gender']} | Возраст: {patient['age']} лет\n"
    #     f"Профессия: {patient['profession']}",
    #     parse_mode="HTML",
    # )
    await cb.message.answer(case.get("greeting", "Добрый день, доктор. Можно войти на приём?"))