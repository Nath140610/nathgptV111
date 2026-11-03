"""Site NathGPT et proxy SSE vers l'API NathGPT V4 (local ou Render + Supabase)."""

from __future__ import annotations

import asyncio
import base64
import binascii
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
from services.store import IMAGE_TYPES, SQLiteStore, StoreError, SupabaseStore, hash_password, verify_password


SITE_DIR = Path(__file__).resolve().parent
COOKIE_NAME = "nathgpt_backend_sid"
COOKIE_AGE = 60 * 60 * 24 * 30
MAX_BODY_BYTES = 64_000
MAX_CONVERSATION_BYTES = 1_000_000
MAX_PROMPT_CHARS = 12_000
MAX_MESSAGES = 500
CONVERSATION_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
IMAGE_NAME_RE = re.compile(r"^[a-f0-9]{32}\.(png|jpg|webp)$")
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_FILES = 5
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES_TOTAL_BYTES = 25 * 1024 * 1024
MAX_CHAT_BODY_BYTES = 36 * 1024 * 1024  # fichiers joints en base64 (+33 %)
PURGE_INTERVAL_SECONDS = 60 * 60
MEMORY_IMAGES_BYTES = 150 * 1024 * 1024
HEARTBEAT_SECONDS = 10
JOB_KEEP_SECONDS = 60 * 60
LOG = logging.getLogger("nathgpt.site")
STATIC_FILES = {
    "": "index.html", "index.html": "index.html", "styles.css": "styles.css",
    "app.js": "app.js", "logo.png": "logo.png", "orbs.bundle.js": "orbs.bundle.js",
    "voice.bundle.js": "voice.bundle.js", "ring.bundle.js": "ring.bundle.js",
    "markdown.bundle.js": "markdown.bundle.js",
    "manifest.webmanifest": "manifest.webmanifest", "sw.js": "sw.js",
}


@dataclass(frozen=True)
class Settings:
    api_url: str = "http://127.0.0.1:18765"
    api_token: str = ""
    database_path: Path = SITE_DIR / "data" / "nathgpt.sqlite3"
    supabase_url: str = ""
    supabase_key: str = ""
    cookie_secure: bool = False


class ChatJob:
    """Réponse en cours ou terminée, gardée 1 h pour être récupérée après une coupure."""

    def __init__(self):
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
        task = asyncio.create_task(purge_forever())
        try:
            yield
        finally:
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

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
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
        return session_response({"ok": True, "account": {"key": key, "pseudo": pseudo, "tokens_used": 0, "usage_estimated": False, "is_admin": False}}, request, sid)

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
                   "is_admin": await store.is_admin(key)}
        return session_response({"ok": True, "account": account}, request, sid)

    @app.get("/api/auth/me")
    async def me(request: Request):
        account = await current_account(request)
        return {"ok": True, "account": {**account, "is_admin": await store.is_admin(account["key"])}}

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
        try:
            storage = await store.image_storage_status()
        except StoreError as error:
            storage = str(error)
        site = {"active_generations": gate.global_active, "image_storage": storage}
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

    @app.post("/api/admin/restart")
    async def admin_restart(request: Request):
        check_origin(request)
        account = await admin_account(request)
        await admin_upstream("POST", "/admin/restart")
        LOG.warning("Relance de NathGPT demandée par %s", account["key"])
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
            data = await store.load_image(account["key"], name)
        if data is None:
            raise HTTPException(404)
        media_type = {v: k for k, v in IMAGE_TYPES.items()}[match.group(1)]
        return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=31536000, immutable"})

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
            """Enregistre l'image (Supabase Storage / disque) et renvoie un lien court au navigateur."""
            decoded = decode_image(data)
            if not decoded:
                return None
            raw, mime_type = decoded
            name = f"{uuid.uuid4().hex}.{IMAGE_TYPES[mime_type]}"
            try:
                await store.save_image(account["key"], name, raw, mime_type)
            except StoreError as error:
                LOG.error("Image non enregistrée dans le stockage (%s) : gardée en mémoire", error)
                remember_image(account["key"], name, raw)
            return {"url": f"/api/images/{name}", "mime_type": mime_type, "filename": data.get("filename") or name}

        job = ChatJob()
        jobs[(account["key"], request_id)] = job

        async def produce():
            """Lit la réponse de l'API jusqu'au bout, même si le navigateur se déconnecte (iPhone en veille…)."""
            answer = ""
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
                        elif kind == "done" and answer.strip():
                            data = await record_usage(answer, data)
                        job.add(kind, data)
                        if kind in ("done", "error"):
                            return
                job.add("done", await record_usage(answer, {}) if answer.strip() else {})
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
