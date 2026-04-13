"""
HTTP-клиент к FastAPI-бэкенду.
Единая сессия aiohttp, понятные исключения BackendError.
"""
import logging
import os
import ssl
import aiohttp
from aiohttp import TCPConnector

logger = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

def _get_connector():
    """Создает новый connector при каждом вызове (внутри асинхронной функции)"""
    return TCPConnector(ssl=ssl_context)

class BackendError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Backend {status}: {detail}")


def _user_id(tg_id: int) -> str:
    return f"tg_{tg_id}"


async def _request(method: str, path: str, **kwargs) -> dict | None:
    url = f"{BACKEND_URL}{path}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **kwargs) as resp:
            if resp.status == 204:
                return None
            body = await resp.json(content_type=None)
            if resp.status >= 400:
                detail = body.get("detail", str(body)) if isinstance(body, dict) else str(body)
                logger.warning("Backend error %d %s: %s", resp.status, path, detail)
                raise BackendError(resp.status, detail)
            return body


# ── Cases ─────────────────────────────────────────────────────────────────────

async def start_case(tg_id: int, disease_type: str | None = None) -> dict:
    body = {"user_id": _user_id(tg_id)}
    if disease_type:
        body["disease_type"] = disease_type
    return await _request("POST", "/api/v1/cases/start", json=body)


async def start_random_case(tg_id: int) -> dict:
    return await _request("POST", "/api/v1/cases/start", json={"user_id": _user_id(tg_id)})


async def start_blind_case(tg_id: int) -> dict:
    return await _request("POST", "/api/v1/cases/start-blind", json={"user_id": _user_id(tg_id)})


async def send_message(session_id: str, text: str) -> dict:
    return await _request("POST", f"/api/v1/cases/{session_id}/message", json={"text": text})


async def submit_diagnosis(session_id: str, diagnosis: str) -> dict:
    return await _request("POST", f"/api/v1/cases/{session_id}/diagnosis", json={"diagnosis": diagnosis})


async def get_session_status(session_id: str) -> dict:
    return await _request("GET", f"/api/v1/cases/{session_id}/status")


async def delete_session(session_id: str) -> None:
    await _request("DELETE", f"/api/v1/cases/{session_id}")


# ── Whitelist ─────────────────────────────────────────────────────────────────

async def ensure_whitelisted(tg_id: int) -> None:
    """Добавляет пользователя в вайтлист если его нет (идемпотентно)."""
    await _request("POST", "/api/v1/whitelist", json={"user_id": _user_id(tg_id)})


async def add_to_whitelist(user_id: str) -> dict:
    return await _request("POST", "/api/v1/whitelist", json={"user_id": user_id})


async def remove_from_whitelist(user_id: str) -> None:
    await _request("DELETE", f"/api/v1/whitelist/{user_id}")


async def get_whitelist() -> dict:
    return await _request("GET", "/api/v1/whitelist")


async def get_whitelist_user(user_id: str) -> dict:
    return await _request("GET", f"/api/v1/whitelist/{user_id}")


# ── Health ────────────────────────────────────────────────────────────────────

async def health_check() -> dict:
    return await _request("GET", "/api/v1/health")