"""
Команды для администратора — управление вайтлистом.
Добавь свой Telegram ID в ADMIN_IDS в .env: ADMIN_IDS=123456789,987654321
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import get_settings
from telegram import api_client as api

router = Router(name="admin")
logger = logging.getLogger(__name__)


def is_admin(tg_id: int) -> bool:
    return tg_id in get_settings().admin_ids


class AdminState(StatesGroup):
    adding_user = State()
    removing_user = State()


# ── Фильтр — только для команд ниже ──────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(msg: Message) -> None:
    if not is_admin(msg.from_user.id):
        return
    await msg.answer(
        "🔐 Панель администратора\n\n"
        "/wl_list — список всех пользователей вайтлиста\n"
        "/wl_add — добавить пользователя\n"
        "/wl_remove — удалить пользователя\n"
        "/wl_check — проверить статус пользователя\n"
        "/health — статус бэкенда",
        parse_mode="HTML",
    )


@router.message(Command("wl_list"))
async def cmd_wl_list(msg: Message) -> None:
    if not is_admin(msg.from_user.id):
        return

    try:
        data = await api.get_whitelist()
    except api.BackendError as e:
        await msg.answer(f"⚠️ Ошибка: {e.detail}")
        return

    entries = data.get("entries", [])
    total = data.get("total", 0)

    if not entries:
        await msg.answer("Вайтлист пуст.")
        return

    icons = {"idle": "⬜", "active": "🟢", "finished": "🔵", "abandoned": "🔴"}
    lines = [f"👥 Вайтлист ({total} чел.):\n"]
    for e in entries:
        icon = icons.get(e["state"], "⚪")
        sid = f"\n    └ сессия: <code>{e['session_id']}</code>" if e.get("session_id") else ""
        lines.append(f"{icon} <code>{e['user_id']}</code> [{e['state']}]{sid}")

    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("wl_add"))
async def cmd_wl_add_start(msg: Message, state: FSMContext) -> None:
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminState.adding_user)
    await msg.answer(
        "Введите user_id для добавления в вайтлист.\n\n"
        "Формат Telegram-пользователей: <code>tg_123456789</code>\n"
        "Или любой строковый ID.",
        parse_mode="HTML",
    )


@router.message(AdminState.adding_user)
async def cmd_wl_add_handle(msg: Message, state: FSMContext) -> None:
    if not is_admin(msg.from_user.id):
        await state.clear()
        return

    user_id = (msg.text or "").strip()
    if not user_id:
        await msg.answer("Некорректный ввод. Попробуйте снова:")
        return

    await state.clear()
    try:
        result = await api.add_to_whitelist(user_id)
        await msg.answer(
            f"✅ Пользователь <code>{result['user_id']}</code> добавлен.\n"
            f"Статус: {result['state']}",
            parse_mode="HTML",
        )
    except api.BackendError as e:
        await msg.answer(f"⚠️ Ошибка: {e.detail}")


@router.message(Command("wl_remove"))
async def cmd_wl_remove_start(msg: Message, state: FSMContext) -> None:
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminState.removing_user)
    await msg.answer("Введите user_id для удаления из вайтлиста:", parse_mode="HTML")


@router.message(AdminState.removing_user)
async def cmd_wl_remove_handle(msg: Message, state: FSMContext) -> None:
    if not is_admin(msg.from_user.id):
        await state.clear()
        return

    user_id = (msg.text or "").strip()
    if not user_id:
        await msg.answer("Некорректный ввод.")
        return

    await state.clear()
    try:
        await api.remove_from_whitelist(user_id)
        await msg.answer(f"🗑️ Пользователь <code>{user_id}</code> удалён.", parse_mode="HTML")
    except api.BackendError as e:
        if e.status == 404:
            await msg.answer(f"Пользователь <code>{user_id}</code> не найден в вайтлисте.", parse_mode="HTML")
        else:
            await msg.answer(f"⚠️ Ошибка: {e.detail}")


@router.message(Command("wl_check"))
async def cmd_wl_check(msg: Message) -> None:
    if not is_admin(msg.from_user.id):
        return

    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: /wl_check <user_id>")
        return

    user_id = parts[1].strip()
    try:
        entry = await api.get_whitelist_user(user_id)
        icons = {"idle": "⬜", "active": "🟢", "finished": "🔵", "abandoned": "🔴"}
        icon = icons.get(entry["state"], "⚪")
        sid = entry.get("session_id") or "—"
        await msg.answer(
            f"{icon} <code>{entry['user_id']}</code>\n"
            f"Статус: {entry['state']}\n"
            f"Сессия: <code>{sid}</code>\n"
            f"Создан: {entry['created_at']}\n"
            f"Обновлён: {entry['updated_at']}",
            parse_mode="HTML",
        )
    except api.BackendError as e:
        if e.status == 404:
            await msg.answer(f"Пользователь <code>{user_id}</code> не найден в вайтлисте.", parse_mode="HTML")
        else:
            await msg.answer(f"⚠️ Ошибка: {e.detail}")


@router.message(Command("health"))
async def cmd_health(msg: Message) -> None:
    if not is_admin(msg.from_user.id):
        return
    try:
        data = await api.health_check()
        icon = "✅" if data.get("status") == "ok" else "❌"
        await msg.answer(
            f"{icon} Статус бэкенда: {data.get('status')}\n"
            f"Активных сессий: {data.get('active_sessions', '?')}",
            parse_mode="HTML",
        )
    except api.BackendError as e:
        await msg.answer(f"❌ Бэкенд недоступен: {e.detail}")