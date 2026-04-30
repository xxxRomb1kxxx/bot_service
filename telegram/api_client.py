"""
HTTP-клиент к FastAPI-бэкенду.
Единая сессия aiohttp, понятные исключения BackendError.
"""
import logging
import ssl
from datetime import datetime, timedelta, timezone

import jwt
import aiohttp
from aiohttp import TCPConnector

from config import get_settings

logger = logging.getLogger(__name__)

BACKEND_URL = get_settings().backend_url

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

_token_cache: dict[str, dict] = {}


def _user_id(tg_id: int) -> str:
    return f"tg_{tg_id}"


def _get_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    cached = _token_cache.get(user_id)
    if cached and cached["expires_at"] > now + timedelta(seconds=30):
        return cached["token"]

    settings = get_settings()
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    token = jwt.encode(
        {"sub": user_id, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    _token_cache[user_id] = {"token": token, "expires_at": expires_at}
    return token


def _get_connector():
    return TCPConnector(ssl=ssl_context)


class BackendError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Backend {status}: {detail}")


async def _request(method: str, path: str, tg_id: int, **kwargs) -> dict | None:
    url = f"{BACKEND_URL}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_get_token(_user_id(tg_id))}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, headers=headers, **kwargs) as resp:
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
    return await _request("POST", "/api/v1/cases/start", tg_id=tg_id, json=body)


async def start_random_case(tg_id: int) -> dict:
    return await _request("POST", "/api/v1/cases/start", tg_id=tg_id, json={"user_id": _user_id(tg_id)})


async def start_blind_case(tg_id: int) -> dict:
    return await _request("POST", "/api/v1/cases/start-blind", tg_id=tg_id, json={"user_id": _user_id(tg_id)})


async def send_message(session_id: str, text: str, tg_id: int) -> dict:
    return await _request("POST", f"/api/v1/cases/{session_id}/message", tg_id=tg_id, json={"text": text})


async def get_message_result(session_id: str, message_id: str, tg_id: int) -> dict:
    return await _request("GET", f"/api/v1/cases/{session_id}/messages/{message_id}", tg_id=tg_id)


async def submit_diagnosis(session_id: str, diagnosis: str, tg_id: int) -> dict:
    return await _request("POST", f"/api/v1/cases/{session_id}/diagnosis", tg_id=tg_id, json={"diagnosis": diagnosis})


async def get_session_status(session_id: str, tg_id: int) -> dict:
    return await _request("GET", f"/api/v1/cases/{session_id}/status", tg_id=tg_id)


async def delete_session(session_id: str, tg_id: int) -> None:
    await _request("DELETE", f"/api/v1/cases/{session_id}", tg_id=tg_id)


# ── Whitelist ─────────────────────────────────────────────────────────────────

async def ensure_whitelisted(tg_id: int) -> None:
    await _request("POST", "/api/v1/whitelist", tg_id=tg_id, json={"user_id": _user_id(tg_id)})


async def add_to_whitelist(user_id: str, tg_id: int) -> dict:
    return await _request("POST", "/api/v1/whitelist", tg_id=tg_id, json={"user_id": user_id})


async def remove_from_whitelist(user_id: str, tg_id: int) -> None:
    await _request("DELETE", f"/api/v1/whitelist/{user_id}", tg_id=tg_id)


async def get_whitelist(tg_id: int) -> dict:
    return await _request("GET", "/api/v1/whitelist", tg_id=tg_id)


async def get_whitelist_user(user_id: str, tg_id: int) -> dict:
    return await _request("GET", f"/api/v1/whitelist/{user_id}", tg_id=tg_id)


# ── Health ────────────────────────────────────────────────────────────────────

async def health_check(tg_id: int) -> dict:
    return await _request("GET", "/api/v1/health", tg_id=tg_id)
