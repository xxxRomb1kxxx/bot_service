"""
HTTP-клиент к FastAPI-бэкенду.
Аутентификация временно отключена (закомментирована).
"""
import logging
import ssl
# import time  # нужен когда включим auth

import aiohttp

from config import get_settings

logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


class BackendError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Backend {status}: {detail}")


def _user_id(tg_id: int) -> str:
    return f"tg_{tg_id}"


def _backend_url() -> str:
    return get_settings().backend_url


# ── Token cache (отключено) ────────────────────────────────────────────────────
# _token_cache: dict[int, dict] = {}
#
# async def _fetch_token(tg_id: int) -> str:
#     settings = get_settings()
#     headers: dict[str, str] = {}
#     if settings.login_shared_secret:
#         headers["X-Login-Secret"] = settings.login_shared_secret
#     url = f"{_backend_url()}/api/v1/auth/login"
#     async with aiohttp.ClientSession() as session:
#         async with session.post(
#             url, json={"user_id": _user_id(tg_id)}, headers=headers, ssl=ssl_context,
#         ) as resp:
#             body = await resp.json(content_type=None)
#             if resp.status >= 400:
#                 detail = body.get("detail", str(body)) if isinstance(body, dict) else str(body)
#                 raise BackendError(resp.status, detail)
#             token: str = body["access_token"]
#     expires_at = time.monotonic() + settings.token_lifetime_minutes * 60
#     _token_cache[tg_id] = {"token": token, "expires_at": expires_at}
#     return token
#
# async def _get_token(tg_id: int) -> str:
#     cached = _token_cache.get(tg_id)
#     if cached and cached["expires_at"] - time.monotonic() > 30:
#         return cached["token"]
#     return await _fetch_token(tg_id)


# ── Base request ───────────────────────────────────────────────────────────────

async def _request(
    method: str,
    path: str,
    tg_id: int,
    **kwargs,
) -> dict | None:
    # token = await _get_token(tg_id)
    url = f"{_backend_url()}{path}"

    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            url,
            # headers={"Authorization": f"Bearer {token}"},
            ssl=ssl_context,
            **kwargs,
        ) as resp:
            if resp.status == 204:
                return None
            body = await resp.json(content_type=None)
            # if resp.status == 401 and _retry:
            #     _token_cache.pop(tg_id, None)
            #     return await _request(method, path, tg_id, _retry=False, **kwargs)
            if resp.status >= 400:
                detail = body.get("detail", str(body)) if isinstance(body, dict) else str(body)
                logger.warning("Backend error %d %s: %s", resp.status, path, detail)
                raise BackendError(resp.status, detail)
            return body


# ── Cases ──────────────────────────────────────────────────────────────────────

async def start_case(tg_id: int, disease_type: str | None = None) -> dict:
    body: dict = {"user_id": _user_id(tg_id)}
    if disease_type:
        body["disease_type"] = disease_type
    return await _request("POST", "/api/v1/cases/start", tg_id, json=body)


async def start_random_case(tg_id: int) -> dict:
    return await _request("POST", "/api/v1/cases/start", tg_id, json={"user_id": _user_id(tg_id)})


async def start_blind_case(tg_id: int) -> dict:
    return await _request("POST", "/api/v1/cases/start-blind", tg_id, json={"user_id": _user_id(tg_id)})


async def send_message(session_id: str, text: str, tg_id: int) -> dict:
    return await _request(
        "POST", f"/api/v1/cases/{session_id}/message", tg_id, json={"text": text}
    )


async def submit_diagnosis(session_id: str, diagnosis: str, tg_id: int) -> dict:
    return await _request(
        "POST", f"/api/v1/cases/{session_id}/diagnosis", tg_id, json={"diagnosis": diagnosis}
    )


async def get_session_status(session_id: str, tg_id: int) -> dict:
    return await _request("GET", f"/api/v1/cases/{session_id}/status", tg_id)


async def delete_session(session_id: str, tg_id: int) -> None:
    await _request("DELETE", f"/api/v1/cases/{session_id}", tg_id)


# ── Whitelist ──────────────────────────────────────────────────────────────────

async def ensure_whitelisted(tg_id: int) -> None:
    pass  # аутентификация временно отключена
    # url = f"{_backend_url()}/api/v1/whitelist"
    # async with aiohttp.ClientSession() as session:
    #     async with session.post(
    #         url, json={"user_id": _user_id(tg_id)}, ssl=ssl_context,
    #     ) as resp:
    #         if resp.status == 204:
    #             return
    #         body = await resp.json(content_type=None)
    #         if resp.status >= 400:
    #             detail = body.get("detail", str(body)) if isinstance(body, dict) else str(body)
    #             logger.warning("Backend error %d /api/v1/whitelist: %s", resp.status, detail)
    #             raise BackendError(resp.status, detail)


async def add_to_whitelist(user_id: str, tg_id: int) -> dict:
    return await _request("POST", "/api/v1/whitelist", tg_id, json={"user_id": user_id})


async def remove_from_whitelist(user_id: str, tg_id: int) -> None:
    await _request("DELETE", f"/api/v1/whitelist/{user_id}", tg_id)


async def get_whitelist(tg_id: int) -> dict:
    return await _request("GET", "/api/v1/whitelist", tg_id)


async def get_whitelist_user(user_id: str, tg_id: int) -> dict:
    return await _request("GET", f"/api/v1/whitelist/{user_id}", tg_id)


# ── Health ─────────────────────────────────────────────────────────────────────

async def health_check(tg_id: int) -> dict:
    return await _request("GET", "/api/v1/health", tg_id)
