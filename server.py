"""Site NathGPT et proxy SSE vers l'API NathGPT V4 (local ou Render + Supabase)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from services.nathgpt_client import NathGPTClient, SSEProtocolError, UpstreamStatusError
from services.store import IMAGE_TYPES, SQLiteStore, StoreError, SupabaseStore, hash_password, image_folder, verify_password


SITE_DIR = Path(__file__).resolve().parent
COOKIE_NAME = "nathgpt_backend_sid"
COOKIE_AGE = 60 * 60 * 24 * 30
MAX_BODY_BYTES = 64_000
MAX_CONVERSATION_BYTES = 1_000_000
MAX_PROMPT_CHARS = 12_000
MAX_MESSAGES = 500
CONVERSATION_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
IMAGE_NAME_RE = re.compile(r"^[a-f0-9]{32}\.(png|jpg|webp)$")
JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")
CRICUT_FILE_RE = re.compile(r"^(sticker_\d{2}\.png|planche_numerotee\.png)$")
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_FILES = 5
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES_TOTAL_BYTES = 25 * 1024 * 1024
MAX_CHAT_BODY_BYTES = 36 * 1024 * 1024  # fichiers joints en base64 (+33 %)
PURGE_INTERVAL_SECONDS = 60 * 60
MEMORY_IMAGES_BYTES = 150 * 1024 * 1024
HEARTBEAT_SECONDS = 10
GRANT_CHECK_SECONDS = 30
# Compteur d'économies : stocké en tokens (même prix que le site). Une image générée compte 0,050 €.
PRICE_PER_TOKEN_EUR = 0.00000892
IMAGE_COST_EUR = 0.05
IMAGE_TOKENS = round(IMAGE_COST_EUR / PRICE_PER_TOKEN_EUR)
JOB_KEEP_SECONDS = 60 * 60
LOG = logging.getLogger("nathgpt.site")
STATIC_FILES = {
    "": "index.html", "index.html": "index.html", "styles.css": "styles.css",
    "app.js": "app.js", "logo.png": "logo.png", "orbs.bundle.js": "orbs.bundle.js",
    "voice.bundle.js": "voice.bundle.js", "ring.bundle.js": "ring.bundle.js",
    "markdown.bundle.js": "markdown.bundle.js",
    "manifest.webmanifest": "manifest.webmanifest", "sw.js": "sw.js",
    "cricut-bot.bundle.js": "cricut-bot.bundle.js",
}


@dataclass(frozen=True)
class Settings:
    api_url: str = "http://127.0.0.1:18765"
    api_token: str = ""
    database_path: Path = SITE_DIR / "data" / "nathgpt.sqlite3"
    supabase_url: str = ""
    supabase_key: str = ""
    cookie_secure: bool = False
    vapid_public: str = ""
    vapid_private: str = ""
    vapid_subject: str = ""


class ChatJob:
    """Réponse en cours ou terminée, gardée 1 h pour être récupérée après une coupure."""

    def __init__(self, conversation_id: str = ""):
        self.conversation_id = conversation_id
        self.events: list[tuple[str, dict]] = []
        self.answer = ""
        self.images: list[dict] = []
        self.done: dict | None = None
        self.error: dict | None = None
        self.finished = False
        self.finished_at = 0.0
        self.task: asyncio.Task | None = None
        self._changed = asyncio.Event()

    def add(self, kind: str, data: dict) -> None:
        self.events.append((kind, data))
        if kind == "delta":
            self.answer += data.get("text", "")
        elif kind == "replace":
            self.answer = data.get("text", "")
        elif kind == "image":
            self.images.append(data)
        elif kind == "done":
            self.done = data
        elif kind == "error":
            self.error = data
        self._changed.set()

    def finish(self) -> None:
        self.finished = True
        self.finished_at = time.monotonic()
        self._changed.set()

    async def wait(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._changed.wait(), timeout)
        except TimeoutError:
            return False
        self._changed.clear()
        return True

    def summary(self) -> dict:
        return {"finished": self.finished, "answer": self.answer, "images": self.images, "done": self.done, "error": self.error}


class RateGate:
    """Limites par session, IP et nombre de générations Selenium simultanées."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.per_session: dict[str, deque[float]] = defaultdict(deque)
        self.per_ip: dict[str, deque[float]] = defaultdict(deque)
        self.active: set[str] = set()
        self.global_active = 0

    async def acquire(self, sid: str, ip: str) -> None:
        async with self.lock:
            now = time.monotonic()
            for bucket in (self.per_session[sid], self.per_ip[ip]):
                while bucket and now - bucket[0] >= 60:
                    bucket.popleft()
            if len(self.per_session[sid]) >= 12 or len(self.per_ip[ip]) >= 30:
                raise HTTPException(429, detail="Trop de demandes. Réessayez dans une minute.", headers={"Retry-After": "60"})
            if sid in self.active or self.global_active >= 3:
                raise HTTPException(429, detail="NathGPT est occupé. Réessayez dans un instant.", headers={"Retry-After": "5"})
            self.per_session[sid].append(now)
            self.per_ip[ip].append(now)
            self.active.add(sid)
            self.global_active += 1

    async def release(self, sid: str) -> None:
        async with self.lock:
            if sid in self.active:
                self.active.remove(sid)
                self.global_active -= 1


class AuthGate:
    """Freine la recherche de mots de passe : 10 tentatives par minute et par IP."""

    def __init__(self, limit: int = 10):
        self.limit = limit
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, ip: str) -> None:
        now = time.monotonic()
        bucket = self.attempts[ip]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(429, detail="Trop de tentatives. Réessayez dans une minute.", headers={"Retry-After": "60"})
        bucket.append(now)


async def read_json_body(request: Request, limit: int = MAX_BODY_BYTES) -> dict:
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(415, detail="Envoyez du JSON.")
    try:
        content_length = int(request.headers.get("content-length", "0") or "0")
    except ValueError:
        raise HTTPException(400, detail="Longueur de requête invalide.") from None
    if content_length > limit:
        raise HTTPException(413, detail="Requête trop volumineuse.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, detail="Requête trop volumineuse.")
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, detail="JSON invalide.") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, detail="Objet JSON attendu.")
    return payload


def check_origin(request: Request) -> None:
    # Derrière le proxy de Render, seul l'hôte est fiable (le schéma peut être réécrit).
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
        raise HTTPException(403, detail="Origine non autorisée.")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def encode_sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


def estimate_tokens(text: str) -> int:
    size = len(text.encode("utf-8"))
    return max(1, -(-size // 4)) if size else 0


def decode_image(data: dict) -> tuple[bytes, str] | None:
    """Octets d'une image de l'API, vérifiés par leur signature (PNG, JPEG, WebP)."""
    try:
        raw = base64.b64decode(data.get("base64", ""), validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return raw, "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return raw, "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return raw, "image/webp"
    return None


def read_files(payload: dict) -> list[dict]:
    """Fichiers joints du navigateur : [{name, type, base64}] vérifiés puis transmis tels quels à l'API."""
    files = payload.get("files")
    if files is None:
        return []
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise HTTPException(400, detail=f"{MAX_FILES} fichiers maximum par message.")
    checked, total = [], 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("base64"), str):
            raise HTTPException(400, detail="Fichier joint invalide.")
        try:
            size = len(base64.b64decode(item["base64"], validate=True))
        except (binascii.Error, ValueError):
            raise HTTPException(400, detail="Fichier joint illisible.") from None
        name = item.get("name") if isinstance(item.get("name"), str) and item.get("name").strip() else "fichier"
        if not size:
            raise HTTPException(400, detail=f"« {name[:60]} » est vide.")
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, detail=f"« {name[:60]} » dépasse 15 Mo.")
        total += size
        if total > MAX_FILES_TOTAL_BYTES:
            raise HTTPException(413, detail="Fichiers trop volumineux : 25 Mo maximum au total.")
        mime_type = item.get("type") if isinstance(item.get("type"), str) else ""
        checked.append({"filename": name[:120], "mime_type": mime_type[:100], "base64": item["base64"]})
    return checked


def upstream_error(status: int) -> HTTPException:
    if status in (401, 403):
        return HTTPException(502, detail="Le serveur NathGPT refuse son authentification.")
    if status == 429:
        return HTTPException(429, detail="NathGPT est occupé. Réessayez dans un instant.", headers={"Retry-After": "10"})
    if status == 504:
        return HTTPException(504, detail="NathGPT a mis trop de temps à répondre.")
    return HTTPException(502, detail="NathGPT est momentanément indisponible.")


def read_credentials(payload: dict) -> tuple[str, str, str]:
    pseudo = payload.get("pseudo")
    password = payload.get("password")
    if not isinstance(pseudo, str) or not 3 <= len(pseudo.strip()) <= 24 or any(ord(c) < 32 for c in pseudo):
        raise HTTPException(400, detail="Le pseudo doit contenir entre 3 et 24 caractères.")
    if not isinstance(password, str) or not 8 <= len(password) <= 256:
        raise HTTPException(400, detail="Le mot de passe doit contenir au moins 8 caractères.")
    pseudo = pseudo.strip()
    return pseudo, pseudo.casefold(), password


def settings_from_env() -> Settings:
    return Settings(
        api_url=os.getenv("NATHGPT_API_URL", "http://127.0.0.1:18765"),
        api_token=os.getenv("NATHGPT_API_TOKEN", ""),
        database_path=Path(os.getenv("NATHGPT_DB_PATH", str(SITE_DIR / "data" / "nathgpt.sqlite3"))),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        cookie_secure=os.getenv("NATHGPT_COOKIE_SECURE", "").lower() in ("1", "true", "yes") or bool(os.getenv("RENDER")),
        vapid_public=os.getenv("VAPID_PUBLIC_KEY", "").strip(),
        vapid_private=os.getenv("VAPID_PRIVATE_KEY", "").strip(),
        vapid_subject=os.getenv("VAPID_SUBJECT", "").strip(),
    )


def create_app(settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
               store_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or settings_from_env()
    if settings.supabase_url and settings.supabase_key:
        store = SupabaseStore(settings.supabase_url, settings.supabase_key, transport=store_transport)
    else:
        store = SQLiteStore(settings.database_path)
    gate = RateGate()
    auth_gate = AuthGate()
    client = NathGPTClient(settings.api_url, settings.api_token, transport=transport)
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Images générées : gardées 1 jour. Nettoyage au démarrage, puis toutes les heures.
        async def purge_forever():
            while True:
                try:
                    removed = await store.purge_images()
                    if removed:
                        LOG.info("%s image(s) de plus d'un jour supprimée(s)", removed)
                except Exception:
                    LOG.warning("Nettoyage des images impossible", exc_info=True)
                await asyncio.sleep(PURGE_INTERVAL_SECONDS)
        async def grants_forever():
            while True:
                try:
                    await apply_due_grants()
                except Exception:
                    LOG.warning("Application des accès programmés impossible", exc_info=True)
                await asyncio.sleep(GRANT_CHECK_SECONDS)
        tasks = [asyncio.create_task(purge_forever()), asyncio.create_task(grants_forever())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()

    app = FastAPI(title="NathGPT", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    jobs: dict[tuple[str, str], ChatJob] = {}

    def prune_jobs() -> None:
        limit = time.monotonic() - JOB_KEEP_SECONDS
        for job_key in [k for k, job in jobs.items() if job.finished and job.finished_at < limit]:
            del jobs[job_key]
    # Secours si Supabase Storage refuse l'image : gardée en mémoire (perdue au redémarrage du serveur).
    memory_images: OrderedDict[tuple[str, str], bytes] = OrderedDict()

    def remember_image(key: str, name: str, data: bytes) -> None:
        memory_images[(key, name)] = data
        while sum(len(value) for value in memory_images.values()) > MEMORY_IMAGES_BYTES and len(memory_images) > 1:
            memory_images.popitem(last=False)
    app.state.gate = gate

    @app.exception_handler(StoreError)
    async def store_unavailable(_request: Request, _error: StoreError):
        return JSONResponse({"detail": "La base de données est momentanément indisponible."}, status_code=503)

    seen_url = {"value": os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")}

    def public_url() -> str:
        """Adresse publique du site (contact VAPID des notifications envoyées hors requête)."""
        return seen_url["value"] or "https://localhost"  # Render fournit RENDER_EXTERNAL_URL

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if not seen_url["value"] and request.url.scheme == "https":
            seen_url["value"] = str(request.base_url).rstrip("/")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def session_response(payload: dict, request: Request, sid: str) -> JSONResponse:
        response = JSONResponse(payload)
        secure = settings.cookie_secure or request.url.scheme == "https"
        response.set_cookie(COOKIE_NAME, sid, max_age=COOKIE_AGE, httponly=True, secure=secure, samesite="lax", path="/")
        return response

    async def current_account(request: Request) -> dict:
        account = await store.session_account(request.cookies.get(COOKIE_NAME))
        if not account:
            raise HTTPException(401, detail="Session expirée. Reconnectez-vous.")
        return account

    @app.get("/api/health")
    @app.get("/health")
    async def health():
        return {"status": "ok", "api_configured": bool(client.token), "storage": store.kind}

    @app.post("/api/auth/signup")
    async def signup(request: Request):
        check_origin(request)
        auth_gate.check(client_ip(request))
        pseudo, key, password = read_credentials(await read_json_body(request, 4096))
        password_hash = await asyncio.to_thread(hash_password, password)
        if not await store.create_account(key, pseudo, password_hash):
            raise HTTPException(409, detail="Ce pseudo est déjà utilisé.")
        sid = await store.create_session(key)
        return session_response({"ok": True, "account": {"key": key, "pseudo": pseudo, "tokens_used": 0, "usage_estimated": False, "is_admin": False, "cricut": False}}, request, sid)

    @app.post("/api/auth/login")
    async def login(request: Request):
        check_origin(request)
        auth_gate.check(client_ip(request))
        _pseudo, key, password = read_credentials(await read_json_body(request, 4096))
        saved = await store.get_account(key)
        if not saved or not await asyncio.to_thread(verify_password, saved["password_hash"], password):
            raise HTTPException(401, detail="Pseudo ou mot de passe incorrect.")
        await store.revoke(request.cookies.get(COOKIE_NAME))
        sid = await store.create_session(key)
        account = {"key": saved["key"], "pseudo": saved["pseudo"], "tokens_used": int(saved.get("tokens_used") or 0), "usage_estimated": bool(saved.get("usage_estimated")),
                   "is_admin": await store.is_admin(key), "cricut": await store.is_cricut(key)}
        return session_response({"ok": True, "account": account}, request, sid)

    @app.get("/api/auth/me")
    async def me(request: Request):
        account = await current_account(request)
        return {"ok": True, "account": {**account, "is_admin": await store.is_admin(account["key"]), "cricut": await store.is_cricut(account["key"])}}

    @app.post("/api/session/logout")
    async def logout(request: Request):
        check_origin(request)
        await store.revoke(request.cookies.get(COOKIE_NAME))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    # Administration : réservée aux comptes dont la case is_admin est cochée dans Supabase.
    async def admin_account(request: Request) -> dict:
        account = await current_account(request)
        if not await store.is_admin(account["key"]):
            raise HTTPException(403, detail="Accès réservé aux administrateurs.")
        return account

    async def admin_upstream(method: str, path: str, json_body: dict | None = None) -> httpx.Response:
        try:
            response = await client.admin(method, path, json_body)
        except httpx.HTTPError:
            raise HTTPException(502, detail="La VM NathGPT ne répond pas.") from None
        if response.status_code == 401:
            raise HTTPException(502, detail="Token API refusé par la VM.")
        if response.status_code == 404:
            raise HTTPException(502, detail="API de la VM trop ancienne : relance TOUT_FAIRE_TOUT_SEUL.bat.")
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = "La VM NathGPT a renvoyé une erreur."
            raise HTTPException(502, detail=str(message)[:300])
        return response

    @app.get("/api/admin/status")
    async def admin_status(request: Request):
        await admin_account(request)
        site = {"active_generations": gate.global_active}
        try:
            vm = (await admin_upstream("GET", "/admin/status")).json()
        except HTTPException as error:
            return {"ok": True, "online": False, "message": error.detail, **site}
        return {"ok": True, "online": True, "vm": vm, **site}

    @app.get("/api/admin/screenshot")
    async def admin_screenshot(request: Request):
        await admin_account(request)
        response = await admin_upstream("GET", "/admin/screenshot")
        if response.headers.get("content-type", "").split(";")[0] != "image/jpeg" or len(response.content) > MAX_IMAGE_BYTES:
            raise HTTPException(502, detail="Capture d'écran invalide.")
        return Response(response.content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/admin/logs")
    async def admin_logs(request: Request):
        await admin_account(request)
        lines = (await admin_upstream("GET", "/admin/logs")).json().get("lines") or []
        return {"ok": True, "lines": [str(line)[:2000] for line in lines[-200:]]}

    @app.post("/api/admin/input")
    async def admin_input(request: Request):
        """Contrôle à distance : clic, molette, touche ou texte, vérifiés ici puis par la VM."""
        check_origin(request)
        await admin_account(request)
        payload = await read_json_body(request, 8192)
        allowed = {"action", "x", "y", "button", "double", "steps", "key", "text"}
        if payload.get("action") not in ("click", "scroll", "key", "text") or set(payload) - allowed:
            raise HTTPException(400, detail="Action invalide.")
        await admin_upstream("POST", "/admin/input", payload)
        return {"ok": True}

    @app.post("/api/admin/release")
    async def admin_release(request: Request):
        """Libère l'état « génère une réponse » quand il reste bloqué."""
        check_origin(request)
        account = await admin_account(request)
        result = (await admin_upstream("POST", "/admin/release")).json()
        LOG.warning("Libération de NathGPT demandée par %s (%s)", account["key"], result.get("was"))
        return {"ok": True, "released": result.get("released") is True, "was": result.get("was")}

    @app.post("/api/admin/restart")
    async def admin_restart(request: Request):
        check_origin(request)
        account = await admin_account(request)
        await admin_upstream("POST", "/admin/restart")
        LOG.warning("Relance de NathGPT demandée par %s", account["key"])
        return {"ok": True}

    async def charge_images(account_key: str, count: int) -> int | None:
        """Ajoute 0,050 € par image générée au compteur ; renvoie le nouveau total (en tokens)."""
        if count <= 0:
            return None
        try:
            return await store.add_usage(account_key, IMAGE_TOKENS * count, False)
        except StoreError:
            return None

    # ----- Images générées : stockées sur la VM (supprimées par elle après 4 h) -----
    async def vm_save_image(account_key: str, name: str, data: bytes) -> None:
        path = f"/storage/images/{image_folder(account_key)}/{name}"
        try:
            response = await client.admin("PUT", path, content=data, read_timeout=60)
        except httpx.HTTPError as error:
            raise StoreError("VM injoignable") from error
        if response.status_code != 200:
            raise StoreError(f"VM : stockage refusé (HTTP {response.status_code})")

    async def vm_load_image(account_key: str, name: str) -> bytes | None:
        try:
            response = await client.admin("GET", f"/storage/images/{image_folder(account_key)}/{name}", read_timeout=60)
        except httpx.HTTPError:
            return None
        return response.content if response.status_code == 200 else None

    # ----- Notifications push (VAPID) -----
    PUSH_FIELD_RE = re.compile(r"^[A-Za-z0-9_=-]{1,200}$")

    async def send_push(account_key: str, payload: dict, subject: str) -> int:
        """Envoie une notification à tous les appareils abonnés du compte. Renvoie le nombre d'envois réussis."""
        if not (settings.vapid_public and settings.vapid_private):
            return 0
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:
            LOG.warning("pywebpush absent : notification push non envoyée")
            return 0
        sent = 0
        for sub in await store.list_push_subscriptions(account_key):
            info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
            try:
                await asyncio.to_thread(webpush, subscription_info=info, data=json.dumps(payload),
                                        vapid_private_key=settings.vapid_private,
                                        vapid_claims={"sub": settings.vapid_subject or subject}, ttl=86400)
                sent += 1
            except WebPushException as error:
                status = getattr(error.response, "status_code", None)
                if status in (404, 410):  # appareil désabonné
                    with contextlib.suppress(StoreError):
                        await store.delete_push_subscription(sub["endpoint"])
                else:
                    LOG.warning("Notification push refusée (%s)", status)
            except Exception:
                LOG.warning("Notification push impossible", exc_info=True)
        return sent

    @app.get("/api/push/key")
    async def push_key():
        return {"key": settings.vapid_public or None}

    @app.post("/api/push/subscribe")
    async def push_subscribe(request: Request):
        check_origin(request)
        account = await current_account(request)
        payload = await read_json_body(request, 4096)
        endpoint = payload.get("endpoint")
        keys = payload.get("keys") if isinstance(payload.get("keys"), dict) else {}
        p256dh, auth = keys.get("p256dh"), keys.get("auth")
        if not isinstance(endpoint, str) or not endpoint.startswith("https://") or len(endpoint) > 1000:
            raise HTTPException(400, detail="Abonnement invalide.")
        if not all(isinstance(value, str) and PUSH_FIELD_RE.fullmatch(value) for value in (p256dh, auth)):
            raise HTTPException(400, detail="Abonnement invalide.")
        await store.save_push_subscription(account["key"], endpoint, p256dh, auth)
        return {"ok": True}

    # ----- Mode Cricut (comptes dont la case cricut est cochée) -----
    notified_jobs: set[str] = set()

    async def cricut_account(request: Request) -> dict:
        account = await current_account(request)
        if not await store.is_cricut(account["key"]):
            raise HTTPException(403, detail="Le mode Cricut n'est pas activé pour ce compte.")
        return account

    async def cricut_vm(method: str, path: str, account: dict, *, json_body: dict | None = None, read_timeout: float = 30,
                        params: dict | None = None) -> httpx.Response:
        try:
            response = await client.admin(method, path, json_body, params={"owner": account["key"], **(params or {})}, read_timeout=read_timeout)
        except httpx.HTTPError:
            raise HTTPException(502, detail="La VM NathGPT ne répond pas.") from None
        if response.status_code < 400:
            return response
        try:
            message = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = ""
        if response.status_code == 404:
            raise HTTPException(404, detail="Planche introuvable (peut-être déjà supprimée).")
        if response.status_code in (400, 409):
            raise HTTPException(response.status_code, detail=message or "Demande refusée par la VM.")
        if response.status_code == 401:
            raise HTTPException(502, detail="Token API refusé par la VM.")
        raise HTTPException(502, detail="La VM NathGPT a renvoyé une erreur.")

    def check_job_id(job_id: str) -> None:
        if not JOB_ID_RE.fullmatch(job_id):
            raise HTTPException(404, detail="Planche introuvable.")

    @app.get("/api/cricut/jobs")
    async def cricut_list(request: Request):
        account = await cricut_account(request)
        return (await cricut_vm("GET", "/cricut/jobs", account)).json()

    @app.post("/api/cricut/jobs")
    async def cricut_create(request: Request):
        check_origin(request)
        account = await cricut_account(request)
        payload = await read_json_body(request, MAX_CHAT_BODY_BYTES)
        image, mime_type = payload.get("image"), payload.get("type")
        if not isinstance(image, str) or mime_type not in ("image/png", "image/jpeg", "image/webp"):
            raise HTTPException(400, detail="Envoie une image PNG, JPEG ou WebP.")
        name = payload.get("name") if isinstance(payload.get("name"), str) else "planche"
        body = {"owner": account["key"], "image": image, "mime_type": mime_type, "filename": name[:120],
                "callback_url": str(request.base_url).rstrip("/") + "/api/cricut/callback"}
        return (await cricut_vm("POST", "/cricut/jobs", account, json_body=body, read_timeout=60)).json()

    @app.get("/api/cricut/jobs/{job_id}")
    async def cricut_get(job_id: str, request: Request):
        account = await cricut_account(request)
        check_job_id(job_id)
        return (await cricut_vm("GET", f"/cricut/jobs/{job_id}", account)).json()

    @app.delete("/api/cricut/jobs/{job_id}")
    async def cricut_remove(job_id: str, request: Request):
        check_origin(request)
        account = await cricut_account(request)
        check_job_id(job_id)
        return (await cricut_vm("DELETE", f"/cricut/jobs/{job_id}", account)).json()

    @app.get("/api/cricut/jobs/{job_id}/files/{name}")
    async def cricut_file(job_id: str, name: str, request: Request, download: int = 0):
        account = await cricut_account(request)
        check_job_id(job_id)
        if not CRICUT_FILE_RE.fullmatch(name):
            raise HTTPException(404, detail="Fichier introuvable.")
        response = await cricut_vm("GET", f"/cricut/jobs/{job_id}/files/{name}", account, read_timeout=60,
                                   params={"download": "1"} if download == 1 else None)
        headers = {"Cache-Control": "no-store"}
        if download == 1:
            headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return Response(response.content, media_type="image/png", headers=headers)

    @app.get("/api/cricut/jobs/{job_id}/zip")
    async def cricut_zip(job_id: str, request: Request):
        account = await cricut_account(request)
        check_job_id(job_id)
        response = await cricut_vm("GET", f"/cricut/jobs/{job_id}/zip", account, read_timeout=120)
        return Response(response.content, media_type="application/zip",
                        headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="stickers-cricut.zip"'})

    @app.post("/api/cricut/callback")
    async def cricut_callback(request: Request):
        """Appelé par la VM à chaque étape : garde Render éveillé et notifie l'utilisateur à la fin."""
        supplied = request.headers.get("authorization", "")
        if not client.token or not hmac.compare_digest(supplied, f"Bearer {client.token}"):
            raise HTTPException(401)
        job = await read_json_body(request, 16_384)
        job_id, owner, phase = job.get("id"), job.get("owner"), job.get("phase")
        if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id) or not isinstance(owner, str):
            raise HTTPException(400)
        if phase in ("finished", "error") and job_id not in notified_jobs:
            notified_jobs.add(job_id)
            # Chaque image générée (planche numérotée + stickers) compte 0,050 €.
            await charge_images(owner, int(bool(job.get("numbered"))) + int(job.get("completed") or 0))
            if phase == "finished":
                count = int(job.get("completed") or 0)
                payload = {"title": "Tes stickers sont prêts ✂️", "body": f"Cricutastrophe a découpé {count} sticker{'s' if count > 1 else ''}. Télécharge-les vite : ils sont supprimés 10 min après.", "view": "cricut", "tag": f"cricut-{job_id}"}
            else:
                payload = {"title": "Cricutastrophe s'est arrêté", "body": str(job.get("error") or "La planche n'a pas pu être traitée.")[:160], "view": "cricut", "tag": f"cricut-{job_id}"}
            await send_push(owner, payload, str(request.base_url).rstrip("/"))
        return {"ok": True}

    # ----- Rôles : un admin donne un accès tout de suite ou le programme (date et heure) -----
    ROLE_LABELS = {"cricut": "l’accès Cricut", "is_admin": "l’accès Administration"}
    ROLE_VIEWS = {"cricut": "cricut", "is_admin": "admin"}
    last_grant_check = 0.0

    async def apply_due_grants() -> int:
        """Applique les accès arrivés à échéance et prévient chaque personne (notification push)."""
        nonlocal last_grant_check
        last_grant_check = time.monotonic()
        applied = 0
        for grant in await store.claim_due_grants(time.time()):
            if not await store.set_role(grant["account_key"], grant["role"], True):
                continue
            applied += 1
            LOG.info("Accès %s donné à %s", grant["role"], grant["account_key"])
            label = ROLE_LABELS[grant["role"]]
            await send_push(grant["account_key"], {
                "title": "Nouvel accès 🎉", "body": f"Tu viens de recevoir {label} ! Ouvre le menu de ton profil pour l’essayer.",
                "view": ROLE_VIEWS[grant["role"]], "tag": f"role-{grant['id']}",
            }, public_url())
        return applied

    async def maybe_apply_grants() -> None:
        # Render gratuit peut dormir : chaque visite rattrape aussi les accès programmés en retard.
        if time.monotonic() - last_grant_check > 15:
            with contextlib.suppress(StoreError):
                await apply_due_grants()

    def parse_role(value) -> str:
        if value not in ROLE_LABELS:
            raise HTTPException(400, detail="Rôle inconnu.")
        return value

    @app.get("/api/admin/accounts")
    async def admin_accounts(request: Request):
        await admin_account(request)
        return {"ok": True, "accounts": await store.list_accounts()}

    @app.get("/api/admin/grants")
    async def admin_grants(request: Request):
        await admin_account(request)
        grants = await store.list_pending_grants()
        return {"ok": True, "grants": [{**g, "grant_at": int(g["grant_at"] * 1000)} for g in grants]}

    @app.post("/api/admin/grants")
    async def admin_grant(request: Request):
        """Donne un rôle maintenant (grant_at absent) ou le programme (grant_at en millisecondes)."""
        check_origin(request)
        admin = await admin_account(request)
        payload = await read_json_body(request, 2048)
        role, key = parse_role(payload.get("role")), payload.get("account_key")
        if not isinstance(key, str) or not await store.get_account(key):
            raise HTTPException(404, detail="Compte introuvable.")
        when = payload.get("grant_at")
        now = time.time()
        if when is None:
            grant_at = now
        elif isinstance(when, (int, float)) and not isinstance(when, bool):
            grant_at = when / 1000
            if grant_at < now - 60:
                raise HTTPException(400, detail="Choisis une date dans le futur.")
            if grant_at > now + 366 * 86400:
                raise HTTPException(400, detail="Un an maximum.")
        else:
            raise HTTPException(400, detail="Date invalide.")
        grant = await store.create_grant(key, role, grant_at, admin["key"])
        applied = await apply_due_grants() if grant_at <= now + 1 else 0
        return {"ok": True, "applied": bool(applied), "grant": {**grant, "grant_at": int(grant["grant_at"] * 1000)}}

    @app.delete("/api/admin/grants/{grant_id}")
    async def admin_cancel_grant(grant_id: int, request: Request):
        check_origin(request)
        await admin_account(request)
        if not await store.cancel_grant(grant_id):
            raise HTTPException(404, detail="Programmation introuvable (déjà appliquée ?).")
        return {"ok": True}

    @app.post("/api/admin/roles/revoke")
    async def admin_revoke(request: Request):
        check_origin(request)
        admin = await admin_account(request)
        payload = await read_json_body(request, 2048)
        role, key = parse_role(payload.get("role")), payload.get("account_key")
        if role == "is_admin" and key == admin["key"]:
            raise HTTPException(400, detail="Tu ne peux pas retirer ton propre accès admin.")
        if not isinstance(key, str) or not await store.set_role(key, role, False):
            raise HTTPException(404, detail="Compte introuvable.")
        return {"ok": True}

    @app.get("/api/notices")
    async def notices(request: Request):
        """Accès reçus pas encore vus : affichés en bannière dans l'app (si la notification est passée inaperçue)."""
        account = await current_account(request)
        await maybe_apply_grants()
        items = await store.list_notices(account["key"])
        return {"ok": True, "notices": [{"id": n["id"], "role": n["role"], "label": ROLE_LABELS.get(n["role"], n["role"])} for n in items]}

    @app.post("/api/notices/{notice_id}/seen")
    async def notice_seen(notice_id: int, request: Request):
        check_origin(request)
        account = await current_account(request)
        await store.mark_notice_seen(account["key"], notice_id)
        return {"ok": True}

    @app.get("/api/conversations")
    async def list_conversations(request: Request):
        account = await current_account(request)
        return {"conversations": await store.list_conversations(account["key"])}

    @app.put("/api/conversations/{conversation_id}")
    async def save_conversation(conversation_id: str, request: Request):
        check_origin(request)
        account = await current_account(request)
        if not CONVERSATION_RE.fullmatch(conversation_id):
            raise HTTPException(400, detail="Identifiant de conversation invalide.")
        payload = await read_json_body(request, MAX_CONVERSATION_BYTES)
        title, messages = payload.get("title"), payload.get("messages")
        created_at, updated_at = payload.get("created_at"), payload.get("updated_at")
        if not isinstance(title, str) or not isinstance(messages, list) or len(messages) > MAX_MESSAGES or not all(isinstance(m, dict) for m in messages):
            raise HTTPException(400, detail="Conversation invalide.")
        now = int(time.time() * 1000)
        created_at = created_at if isinstance(created_at, int) and not isinstance(created_at, bool) and created_at > 0 else now
        updated_at = updated_at if isinstance(updated_at, int) and not isinstance(updated_at, bool) and updated_at > 0 else now
        if not await store.save_conversation(account["key"], conversation_id, title[:120], messages, created_at, updated_at):
            raise HTTPException(403, detail="Cette conversation appartient à un autre compte.")
        return {"ok": True}

    @app.delete("/api/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str, request: Request):
        check_origin(request)
        account = await current_account(request)
        if CONVERSATION_RE.fullmatch(conversation_id):
            await store.delete_conversation(account["key"], conversation_id)
        return {"ok": True}

    @app.get("/api/images/{name}")
    async def image(name: str, request: Request):
        account = await current_account(request)
        match = IMAGE_NAME_RE.fullmatch(name)
        if not match:
            raise HTTPException(404)
        data = memory_images.get((account["key"], name))
        if data is None:
            data = await vm_load_image(account["key"], name)
        if data is None:  # anciennes images enregistrées dans Supabase
            data = await store.load_image(account["key"], name)
        if data is None:
            raise HTTPException(404)
        media_type = {v: k for k, v in IMAGE_TYPES.items()}[match.group(1)]
        return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=14400"})

    @app.post("/api/chat")
    async def chat(request: Request):
        check_origin(request)
        sid = request.cookies.get(COOKIE_NAME)
        account = await current_account(request)
        payload = await read_json_body(request, MAX_CHAT_BODY_BYTES)
        prompt = payload.get("prompt")
        conversation_id = payload.get("conversation_id")
        if not isinstance(prompt, str) or not prompt.strip():
            raise HTTPException(400, detail="Message vide.")
        prompt = prompt.strip()
        if len(prompt) > MAX_PROMPT_CHARS:
            raise HTTPException(413, detail="Message trop long.")
        if not isinstance(conversation_id, str) or not CONVERSATION_RE.fullmatch(conversation_id):
            raise HTTPException(400, detail="Identifiant de conversation invalide.")
        if payload.get("stream") is not True:
            raise HTTPException(400, detail="Le streaming est obligatoire.")
        if not await store.claim_conversation(account["key"], conversation_id):
            raise HTTPException(403, detail="Cette conversation appartient à un autre compte.")
        files = read_files(payload)
        request_id = payload.get("request_id")
        if request_id is None:
            request_id = uuid.uuid4().hex
        if not isinstance(request_id, str) or not CONVERSATION_RE.fullmatch(request_id):
            raise HTTPException(400, detail="Identifiant de requête invalide.")
        if not client.token:
            raise HTTPException(503, detail="NathGPT API n'est pas configurée sur ce serveur.")
        prune_jobs()
        await gate.acquire(sid, client_ip(request))
        try:
            http_client, upstream = await client.open_stream(prompt, conversation_id, image=payload.get("mode") == "Image", files=files)
        except UpstreamStatusError as error:
            await gate.release(sid)
            raise upstream_error(error.status_code) from None
        except httpx.TimeoutException:
            await gate.release(sid)
            raise HTTPException(504, detail="NathGPT a mis trop de temps à répondre.") from None
        except (httpx.HTTPError, SSEProtocolError):
            await gate.release(sid)
            raise HTTPException(502, detail="Impossible de joindre NathGPT.") from None
        except BaseException:
            await gate.release(sid)
            raise

        async def record_usage(answer: str, done: dict) -> dict:
            """Compteur d'économies côté serveur : tokens annoncés, sinon estimés."""
            exact = done.get("total_tokens")
            tokens = exact if isinstance(exact, int) else estimate_tokens(prompt) + estimate_tokens(answer)
            try:
                total = await store.add_usage(account["key"], tokens, not isinstance(exact, int))
            except StoreError:
                return done
            if total is None:
                return done
            return {**done, "account_tokens_used": total, "usage_estimated": account["usage_estimated"] or not isinstance(exact, int)}

        async def store_image(data: dict) -> dict | None:
            """Enregistre l'image sur la VM (4 h) et renvoie un lien court au navigateur."""
            decoded = decode_image(data)
            if not decoded:
                return None
            raw, mime_type = decoded
            name = f"{uuid.uuid4().hex}.{IMAGE_TYPES[mime_type]}"
            try:
                await vm_save_image(account["key"], name, raw)
            except StoreError as error:
                LOG.error("Image non enregistrée dans le stockage (%s) : gardée en mémoire", error)
                remember_image(account["key"], name, raw)
            return {"url": f"/api/images/{name}", "mime_type": mime_type, "filename": data.get("filename") or name}

        job = ChatJob(conversation_id)
        jobs[(account["key"], request_id)] = job

        async def produce():
            """Lit la réponse de l'API jusqu'au bout, même si le navigateur se déconnecte (iPhone en veille…)."""
            answer = ""
            image_total = None

            async def finish_usage(done: dict) -> dict:
                if answer.strip():
                    return await record_usage(answer, done)
                if image_total is not None:  # réponse image seule : le total inclut déjà les images
                    return {**done, "account_tokens_used": image_total, "usage_estimated": account["usage_estimated"]}
                return done

            try:
                async with asyncio.timeout(360):
                    async for kind, data in client.events(upstream):
                        if kind == "delta":
                            answer += data.get("text", "")
                        elif kind == "replace":
                            answer = data.get("text", "")
                        elif kind == "image":
                            data = await store_image(data)
                            if data is None:
                                job.add("error", {"code": "image_error", "message": "L’image reçue est invalide."})
                                return
                            image_total = await charge_images(account["key"], 1) or image_total
                        elif kind == "done":
                            data = await finish_usage(data)
                        job.add(kind, data)
                        if kind in ("done", "error"):
                            return
                job.add("done", await finish_usage({}))
            except (TimeoutError, httpx.TimeoutException):
                job.add("error", {"code": "timeout", "message": "NathGPT a mis trop de temps à répondre."})
            except (httpx.HTTPError, SSEProtocolError):
                job.add("error", {"code": "upstream_error", "message": "Connexion à NathGPT interrompue."})
            except Exception:
                LOG.exception("Réponse NathGPT interrompue")
                job.add("error", {"code": "upstream_error", "message": "Connexion à NathGPT interrompue."})
            finally:
                job.finish()
                await upstream.aclose()
                await http_client.aclose()
                await gate.release(sid)

        job.task = asyncio.create_task(produce())

        async def event_stream():
            # Un commentaire SSE toutes les 10 s : sans lui, Render coupe la connexion pendant
            # la génération d'une image (1 à 2 min sans texte) et Safari affiche « Load failed ».
            sent = 0
            yield b": ok\n\n"
            while True:
                while sent < len(job.events):
                    kind, data = job.events[sent]
                    sent += 1
                    yield encode_sse(kind, data)
                if job.finished:
                    return
                if not await job.wait(HEARTBEAT_SECONDS):
                    yield b": ping\n\n"

        return StreamingResponse(
            event_stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat/stop")
    async def chat_stop(request: Request):
        """Bouton « Arrêter » : la VM arrête la génération et NathGPT est libéré tout de suite."""
        check_origin(request)
        account = await current_account(request)
        request_id = (await read_json_body(request, 1024)).get("request_id")
        job = jobs.get((account["key"], request_id)) if isinstance(request_id, str) else None
        if not job or job.finished:
            return {"ok": True, "cancelled": False}
        try:
            response = await client.admin("POST", "/v1/cancel", {"conversation_id": job.conversation_id}, read_timeout=10)
            cancelled = response.status_code == 200 and response.json().get("cancelled") is True
        except (httpx.HTTPError, ValueError):
            cancelled = False
        return {"ok": True, "cancelled": cancelled}

    @app.get("/api/chat/result/{request_id}")
    async def chat_result(request_id: str, request: Request):
        """Récupère une réponse après une coupure de connexion (la génération a continué sur le serveur)."""
        account = await current_account(request)
        job = jobs.get((account["key"], request_id)) if CONVERSATION_RE.fullmatch(request_id) else None
        if not job:
            raise HTTPException(404, detail="Réponse introuvable.")
        return job.summary()

    @app.get("/{filename:path}")
    async def static(filename: str):
        name = STATIC_FILES.get(filename)
        if not name:
            raise HTTPException(404)
        path = SITE_DIR / name
        if not path.is_file():
            raise HTTPException(404)
        media_type = "application/manifest+json" if name.endswith(".webmanifest") else None
        response = FileResponse(path, media_type=media_type)
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()
