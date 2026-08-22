from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    session,
    make_response,
    send_from_directory,
    flash,
    stream_with_context,
)

import codecs
import encodings.idna

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from pathlib import Path
from datetime import datetime, timedelta, timezone

import hashlib
import json
import os
import re
import secrets
import threading
import time
import unicodedata
import base64
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from discord_bridge import DiscordBridge


# Certains environnements Python minimalistes ne chargent pas automatiquement
# le codec IDNA, pourtant utilisé par Werkzeug pour lire le nom de domaine.
# Son enregistrement explicite évite les erreurs 500 sur les URL Render.
def ensure_idna_codec():

    try:
        codecs.lookup("idna")
        return
    except LookupError:
        pass


    codecs.register(
        lambda name: (
            encodings.idna.getregentry()
            if name.replace("_", "-") == "idna"
            else None
        )
    )


ensure_idna_codec()


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_DATA_DIR = BASE_DIR / "data"


def get_data_dir():

    configured_dir = Path(
        os.environ.get(
            "NATHGPT_DATA_DIR",
            str(DEFAULT_DATA_DIR)
        )
    )

    try:
        configured_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        return configured_dir

    except PermissionError:
        # Render n'autorise /var/data que lorsqu'un disque persistant est
        # réellement monté. En plan Free, l'application reste fonctionnelle
        # avec un stockage temporaire dans le dossier du projet.
        DEFAULT_DATA_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        print(
            "Stockage persistant indisponible : "
            "utilisation du dossier data temporaire."
        )

        return DEFAULT_DATA_DIR


DATA_DIR = get_data_dir()

USERS_FILE = DATA_DIR / "users.json"

# Les comptes peuvent être déplacés vers Supabase sans changer les routes
# Flask existantes. Le disque local reste une sauvegarde de secours pour les
# conversations et en cas d'indisponibilité temporaire de Supabase.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get(
    "SUPABASE_SECRET_KEY",
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
).strip()
SUPABASE_ACCOUNTS_TABLE = os.environ.get(
    "SUPABASE_ACCOUNTS_TABLE",
    "nathgpt_accounts",
).strip() or "nathgpt_accounts"
SUPABASE_CONVERSATIONS_TABLE = os.environ.get(
    "SUPABASE_CONVERSATIONS_TABLE",
    "nathgpt_conversations",
).strip() or "nathgpt_conversations"

SUPABASE_BUG_REPORTS_TABLE = os.environ.get(
    "SUPABASE_BUG_REPORTS_TABLE",
    "nathgpt_bug_reports",
).strip() or "nathgpt_bug_reports"

SUPABASE_SHARES_TABLE = os.environ.get(
    "SUPABASE_SHARES_TABLE",
    "nathgpt_conversation_shares",
).strip() or "nathgpt_conversation_shares"
SUPABASE_APP_STATE_TABLE = os.environ.get(
    "SUPABASE_APP_STATE_TABLE",
    "nathgpt_app_state",
).strip() or "nathgpt_app_state"

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.environ.get(
    "VAPID_SUBJECT",
    "mailto:admin@example.com",
).strip()

TOKENS_FILE = DATA_DIR / "tokens.json"

CONVERSATIONS_FILE = DATA_DIR / "conversations.json"

AUTOMATIC_GENERATIONS_FILE = DATA_DIR / "automatic_generations.json"

AUTOMATION_STATE_FILE = DATA_DIR / "automation_state.json"

SERVICE_STATUS_FILE = DATA_DIR / "service_status.json"
BUG_REPORTS_FILE = DATA_DIR / "bug_reports.json"
SHARE_LINKS_FILE = DATA_DIR / "conversation_shares.json"

FEATURE_MAINTENANCE_DEFAULTS = {
    "text_generation": {
        "label": "Réponses texte",
        "description": "Désactive uniquement les réponses textuelles envoyées via le chat NathGPT.",
        "default_reason": "Les réponses texte sont temporairement en maintenance. Réessaie dans quelques instants.",
    },
    "image_generation": {
        "label": "Génération d'images",
        "description": "Coupe uniquement les générations et modifications d'images, sans bloquer les réponses texte.",
        "default_reason": "La génération d'images est temporairement en maintenance. Les réponses texte restent disponibles.",
    },
    "cricut": {
        "label": "Mode Cricut",
        "description": "Désactive uniquement l'adaptation Cricut et la découpe automatisée des stickers.",
        "default_reason": "Le mode Cricut est temporairement en maintenance. Réessaie plus tard.",
    },
}

OUTAGE_STAFF_NOTIFICATION_COOLDOWN_SECONDS = 10 * 60
TRIAL_ACCESS_HOURS = 24

try:
    AUTOMATION_TIMEZONE = ZoneInfo("Europe/Paris")
except ZoneInfoNotFoundError:
    # Windows ne fournit pas toujours la base IANA avant l'installation de
    # tzdata. Le repli utilise le fuseau local et évite de bloquer le serveur.
    AUTOMATION_TIMEZONE = datetime.now().astimezone().tzinfo or timezone.utc

AUTOMATION_ENABLED = os.environ.get("AUTOMATION_ENABLED", "true").lower() == "true"

# À modifier avec les notes associées à chaque nouvelle version publiée.
APP_RELEASES = [
    {
        "version": "2026.08.22.1",
        "date": "2026-08-22T13:50:00+02:00",
        "title": "Interface et notifications",
        "additions": [
            "Nouvel écran d'ouverture",
            "Notifications sur les réponses NathGPT",
            "Générations Cricut automatiques et dossiers datés",
        ],
    },
    {
        "version": "2026.08.22.2",
        "date": "2026-08-22T16:20:00+02:00",
        "title": "Persistance et maintenance",
        "additions": [
            "Conversations persistantes synchronisées dans Supabase",
            "Maintenance ciblée : texte, images et Cricut séparément",
        ],
    },
    {
        "version": "2026.08.22.3",
        "date": "2026-08-22T18:38:00+02:00",
        "title": "Historique, partage et outils staff",
        "additions": [
            "Historique avancé des générations avec recherche et filtres",
            "Signalement de bugs depuis le chat",
            "Partage temporaire d'une conversation par lien public",
            "Connexion staff temporaire à un compte utilisateur",
            "Retour haptique sur les appareils compatibles",
            "Nouvel écran de chargement premium",
            "Changelog cumulatif depuis la dernière mise à jour consultée",
        ],
    },
    {
        "version": "2026.08.22.4",
        "title": "Sécurité et maintenance",
        "date": "2026-08-22T18:47:00+02:00",
        "additions": [
            "Captcha simple à la création de compte",
            "Maintenance programmable par fonctionnalité depuis le panneau staff",
            "Planning de maintenance conservé dans Supabase",
        ],
    }
]

APP_RELEASES.append({
    "version": "2026.08.22.5",
    "title": "Personnalisation et statistiques",
    "date": "2026-08-22T18:55:00+02:00",
    "additions": [
        "Conversations épinglables en haut de l'historique",
        "Révocation des liens de partage depuis les paramètres",
        "Mode économie batterie pour réduire les animations",
        "Page Mes statistiques pour chaque utilisateur",
        "Page statistiques détaillées réservée au staff",
        "Nouveaux thèmes : NathGPT, OLED, Océan, Violet et Clair",
    ],
})
APP_RELEASES.append({
    "version": "2026.08.22.6",
    "title": "Tickets et supervision",
    "date": "2026-08-22T19:03:00+02:00",
    "additions": [
        "Signalements transformés en tickets de bugs avec suivi de statut",
        "Taille de la file d'attente visible dans les statistiques staff",
        "Temps moyen des générations affiché dans le panel statistiques",
        "Compteur d'erreurs système sur les dernières 24 heures",
    ],
})
APP_RELEASES.append({
    "version": "2026.08.22.8",
    "title": "Navigation et réactivité",
    "date": "2026-08-22T19:50:00+02:00",
    "additions": [
        "Écran de chargement entièrement circulaire",
        "Historique des générations déplacé dans les paramètres",
        "Mes statistiques regroupées dans les paramètres",
        "Boutons plus réactifs sur ordinateur et mobile",
    ],
})
APP_RELEASE = APP_RELEASES[-1]

BUG_STATUS_LABELS = {
    "new": "Nouveau",
    "in_progress": "En cours",
    "fixed": "Corrigé",
    "closed": "Fermé",
}

THEME_OPTIONS = {
    "nathgpt": {"label": "NathGPT", "color": "#212121"},
    "oled": {"label": "OLED", "color": "#000000"},
    "ocean": {"label": "Océan", "color": "#10212a"},
    "violet": {"label": "Violet", "color": "#211b2d"},
    "light": {"label": "Clair", "color": "#f5f5f7"},
}

SECRET_FILE = DATA_DIR / "secret_key.txt"

discord_bridge = DiscordBridge(DATA_DIR)


# ============================================================
# RECONNEXION AUTOMATIQUE PAR IP
# ============================================================

# True :
# NathGPT peut reconnaître automatiquement un compte
# grâce à son IP si cette IP n'appartient qu'à un seul compte.
#
# False :
# uniquement le cookie de connexion automatique sera utilisé.

ALLOW_IP_AUTOLOGIN = os.environ.get(
    "ALLOW_IP_AUTOLOGIN",
    "false"
).lower() == "true"


# Le mot de passe du panneau staff doit rester dans les variables Render,
# jamais dans le code ni dans un fichier envoyÃ© sur GitHub.
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "")
STAFF_SESSION_SECONDS = 8 * 60 * 60
STAFF_ACTIVE_WINDOW_SECONDS = 10 * 60


# ============================================================
# COOKIE "SE SOUVENIR DE MOI"
# ============================================================

REMEMBER_COOKIE_NAME = "nathgpt_remember"

REMEMBER_DAYS = 90


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 36 * 1024 * 1024


def file_fingerprint(path, fallback="1"):
    """Empreinte courte basée sur le contenu, idéale pour casser le cache navigateur."""
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:12]
    except OSError:
        return str(fallback)


def current_logo_version():
    return file_fingerprint(BASE_DIR / "logo.png")


@app.context_processor
def inject_asset_version():
    try:
        version = int((BASE_DIR / "static" / "style.css").stat().st_mtime)
    except OSError:
        version = 1

    return {
        "asset_version": version,
        "logo_version": current_logo_version(),
    }


# ============================================================
# VERROU POUR LES JSON
# ============================================================

_file_lock = threading.Lock()


# ============================================================
# DATE UTC
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# ECRITURE JSON ATOMIQUE
# ============================================================

def atomic_write_json(path: Path, data):

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    os.replace(
        tmp,
        path
    )


# ============================================================
# CHARGEMENT JSON
# ============================================================

def supabase_accounts_enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def supabase_conversations_enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def supabase_app_state_enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def supabase_request(method, path, payload=None, extra_headers=None):
    """Appelle l'API REST Supabase depuis le serveur uniquement."""
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{SUPABASE_URL}/rest/v1/{path.lstrip('/')}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("Connexion Supabase indisponible.") from error


def load_supabase_accounts():
    rows = supabase_request(
        "GET",
        f"{SUPABASE_ACCOUNTS_TABLE}?select=username,data",
    ) or []

    accounts = {}
    for row in rows:
        username = str(row.get("username", "")).strip()
        details = row.get("data")
        if username and isinstance(details, dict):
            accounts[username] = details
    return accounts


def save_supabase_accounts(accounts):
    rows = [
        {"username": str(username), "data": details}
        for username, details in accounts.items()
        if isinstance(details, dict)
    ]
    existing_rows = supabase_request(
        "GET",
        f"{SUPABASE_ACCOUNTS_TABLE}?select=username",
    ) or []
    existing_names = {
        str(row.get("username", ""))
        for row in existing_rows
        if row.get("username")
    }
    wanted_names = {row["username"] for row in rows}

    if rows:
        supabase_request(
            "POST",
            f"{SUPABASE_ACCOUNTS_TABLE}?on_conflict=username",
            rows,
            {"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    for username in existing_names - wanted_names:
        supabase_request(
            "DELETE",
            f"{SUPABASE_ACCOUNTS_TABLE}?username=eq.{quote(username, safe='')}",
            extra_headers={"Prefer": "return=minimal"},
        )


def load_supabase_conversations():
    rows = supabase_request(
        "GET",
        f"{SUPABASE_CONVERSATIONS_TABLE}?select=username,data",
    ) or []

    conversations = {}
    for row in rows:
        username = str(row.get("username", "")).strip()
        items = row.get("data")
        if username and isinstance(items, list):
            conversations[username] = items
    return conversations


def save_supabase_conversations(conversations):
    if not isinstance(conversations, dict):
        conversations = {}

    rows = [
        {"username": str(username), "data": items}
        for username, items in conversations.items()
        if isinstance(items, list)
    ]

    existing_rows = supabase_request(
        "GET",
        f"{SUPABASE_CONVERSATIONS_TABLE}?select=username",
    ) or []
    existing_names = {
        str(row.get("username", ""))
        for row in existing_rows
        if row.get("username")
    }
    wanted_names = {row["username"] for row in rows}

    if rows:
        supabase_request(
            "POST",
            f"{SUPABASE_CONVERSATIONS_TABLE}?on_conflict=username",
            rows,
            {"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    for username in existing_names - wanted_names:
        supabase_request(
            "DELETE",
            f"{SUPABASE_CONVERSATIONS_TABLE}?username=eq.{quote(username, safe='')}",
            extra_headers={"Prefer": "return=minimal"},
        )



def load_supabase_app_state():
    rows = supabase_request(
        "GET",
        f"{SUPABASE_APP_STATE_TABLE}?key=eq.service_status&select=data&limit=1",
    ) or []
    if not rows:
        return {}
    data = rows[0].get("data")
    return data if isinstance(data, dict) else {}


def save_supabase_app_state(state):
    if not isinstance(state, dict):
        state = {}
    supabase_request(
        "POST",
        f"{SUPABASE_APP_STATE_TABLE}?on_conflict=key",
        [{"key": "service_status", "data": state}],
        {"Prefer": "resolution=merge-duplicates,return=minimal"},
    )


def load_local_json(path: Path, default):
    if not path.exists():
        atomic_write_json(path, default)
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def load_json(path: Path, default):

    with _file_lock:
        if path == USERS_FILE and supabase_accounts_enabled():
            try:
                accounts = load_supabase_accounts()
                # Première migration : les anciens comptes locaux sont envoyés
                # automatiquement si la table Supabase est encore vide.
                if not accounts:
                    local_accounts = load_local_json(path, default)
                    if local_accounts:
                        save_supabase_accounts(local_accounts)
                        return local_accounts
                return accounts
            except RuntimeError:
                print("Supabase comptes indisponible : utilisation temporaire de la sauvegarde locale.")

        if path == CONVERSATIONS_FILE and supabase_conversations_enabled():
            try:
                conversations = load_supabase_conversations()
                # Migration automatique de l'historique local vers Supabase.
                # Elle ne se déclenche que si la table Supabase est vide.
                if not conversations:
                    local_conversations = load_local_json(path, default)
                    if local_conversations:
                        save_supabase_conversations(local_conversations)
                        return local_conversations
                return conversations
            except RuntimeError:
                print("Supabase conversations indisponible : utilisation temporaire de la sauvegarde locale.")

        if path == SERVICE_STATUS_FILE and supabase_app_state_enabled():
            try:
                remote_state = load_supabase_app_state()
                if remote_state:
                    return remote_state
                local_state = load_local_json(path, default)
                if local_state:
                    save_supabase_app_state(local_state)
                return local_state
            except RuntimeError:
                print("Supabase état application indisponible : utilisation temporaire de la sauvegarde locale.")

        return load_local_json(path, default)


# ============================================================
# SAUVEGARDE JSON
# ============================================================

def save_json(path: Path, data):

    with _file_lock:
        if path == USERS_FILE and supabase_accounts_enabled():
            try:
                save_supabase_accounts(data)
            except RuntimeError:
                print("Écriture Supabase comptes impossible : sauvegarde locale conservée.")

        if path == CONVERSATIONS_FILE and supabase_conversations_enabled():
            try:
                save_supabase_conversations(data)
            except RuntimeError:
                print("Écriture Supabase conversations impossible : sauvegarde locale conservée.")

        if path == SERVICE_STATUS_FILE and supabase_app_state_enabled():
            try:
                save_supabase_app_state(data)
            except RuntimeError:
                print("Écriture Supabase état application impossible : sauvegarde locale conservée.")

        # Une copie locale reste conservée comme cache/fallback. Supabase est
        # la source persistante principale lorsque les variables sont configurées.
        atomic_write_json(
            path,
            data
        )


# ============================================================
# HISTORIQUE DES CONVERSATIONS
# ============================================================

def save_conversation_message(
    username,
    conversation_id,
    role,
    content,
    image_url=None,
    cricut_images=None,
):

    conversations = load_json(
        CONVERSATIONS_FILE,
        {}
    )

    user_conversations = conversations.setdefault(
        username,
        []
    )

    conversation = next(
        (
            item
            for item in user_conversations
            if item.get("id") == conversation_id
        ),
        None
    )

    now = utc_now()

    if not conversation:

        conversation = {
            "id": conversation_id,
            "title": "Nouvelle discussion",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }

        user_conversations.append(
            conversation
        )

    clean_content = str(content or "").strip()[:4000]

    if role == "user" and conversation["title"] == "Nouvelle discussion":
        conversation["title"] = clean_content[:80] or "Nouvelle discussion"

    message = {
        "role": role,
        "content": clean_content,
        "created_at": now,
    }

    if image_url:
        message["image_url"] = str(image_url)[:2000]

    if cricut_images is not None:
        message["cricut_images"] = [
            str(url)[:2000]
            for url in cricut_images
            if str(url).strip()
        ][:300]

    conversation["messages"].append(
        message
    )

    # Garde l'historique utile sans faire grossir le fichier indéfiniment.
    conversation["messages"] = conversation["messages"][-200:]
    conversation["updated_at"] = now

    save_json(
        CONVERSATIONS_FILE,
        conversations
    )


def get_conversation_summaries(username):

    conversations = load_json(
        CONVERSATIONS_FILE,
        {}
    )

    owner = next(
        (key for key in conversations if key.casefold() == username.casefold()),
        username,
    )
    items = conversations.get(owner, [])
    if not isinstance(items, list):
        items = []

    ordered = sorted(
        items,
        key=lambda item: (
            1 if item.get("pinned") else 0,
            str(item.get("pinned_at") or item.get("updated_at") or ""),
            str(item.get("updated_at") or ""),
        ),
        reverse=True,
    )

    return [
        {
            "id": item.get("id"),
            "title": item.get("title", "Nouvelle discussion"),
            "updated_at": item.get("updated_at"),
            "pinned": bool(item.get("pinned")),
        }
        for item in ordered
    ]


def get_conversation(username, conversation_id):

    conversations = load_json(
        CONVERSATIONS_FILE,
        {}
    )

    for item in conversations.get(username, []):
        if item.get("id") == conversation_id:
            return item

    return None


def get_pending_releases(user_details):
    seen_version = str((user_details or {}).get("changelog_seen_version") or "").strip()
    if not seen_version:
        return APP_RELEASES

    seen_index = next(
        (index for index, release in enumerate(APP_RELEASES) if release.get("version") == seen_version),
        -1,
    )
    if seen_index < 0:
        return APP_RELEASES
    return APP_RELEASES[seen_index + 1:]


def flatten_generation_history(username):
    conversations = load_json(CONVERSATIONS_FILE, {})
    owner = next((key for key in conversations if key.casefold() == username.casefold()), username)
    history = []
    for conversation in conversations.get(owner, []):
        conversation_id = str(conversation.get("id") or "")
        title = str(conversation.get("title") or "Nouvelle discussion")
        messages = conversation.get("messages", []) if isinstance(conversation, dict) else []
        last_prompt = ""
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "user":
                last_prompt = str(message.get("content") or "")[:300]
                continue
            image_url = str(message.get("image_url") or "").strip()
            if image_url:
                history.append({
                    "id": f"{conversation_id}-{len(history)}",
                    "type": "image",
                    "conversation_id": conversation_id,
                    "conversation_title": title,
                    "prompt": last_prompt,
                    "created_at": message.get("created_at"),
                    "image_url": image_url,
                })
            for image in message.get("cricut_images", []) or []:
                if str(image).strip():
                    history.append({
                        "id": f"{conversation_id}-cricut-{len(history)}",
                        "type": "cricut",
                        "conversation_id": conversation_id,
                        "conversation_title": title,
                        "prompt": last_prompt or "Adaptation Cricut",
                        "created_at": message.get("created_at"),
                        "image_url": str(image),
                    })
    history.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return history[:500]


def _decorate_bug_report(report):
    item = dict(report or {})
    status = str(item.get("status") or "new")
    if status not in BUG_STATUS_LABELS:
        status = "new"
    item["status"] = status
    item["status_label"] = BUG_STATUS_LABELS[status]
    return item


def get_staff_bug_reports(limit=50):
    reports = []
    if supabase_accounts_enabled():
        try:
            rows = supabase_request(
                "GET",
                f"{SUPABASE_BUG_REPORTS_TABLE}?select=id,username,category,description,conversation_id,device,created_at,status&order=created_at.desc&limit={int(limit)}",
            ) or []
            reports = [_decorate_bug_report(row) for row in rows if isinstance(row, dict)]
        except RuntimeError:
            reports = []
    if not reports:
        local_reports = load_local_json(BUG_REPORTS_FILE, [])
        if isinstance(local_reports, list):
            reports = [
                _decorate_bug_report(item)
                for item in reversed(local_reports)
                if isinstance(item, dict)
            ][:limit]
    return reports


def get_user_bug_reports(username, limit=50):
    reports = []
    if supabase_accounts_enabled():
        try:
            rows = supabase_request(
                "GET",
                (
                    f"{SUPABASE_BUG_REPORTS_TABLE}"
                    f"?username=eq.{quote(username, safe='')}"
                    "&select=id,username,category,description,conversation_id,device,created_at,status"
                    f"&order=created_at.desc&limit={int(limit)}"
                ),
            ) or []
            reports = [_decorate_bug_report(row) for row in rows if isinstance(row, dict)]
        except RuntimeError:
            reports = []

    if not reports:
        local_reports = load_local_json(BUG_REPORTS_FILE, [])
        if isinstance(local_reports, list):
            reports = [
                _decorate_bug_report(item)
                for item in reversed(local_reports)
                if isinstance(item, dict)
                and str(item.get("username") or "").casefold() == username.casefold()
            ][:limit]
    return reports


def _new_bug_ticket_id():
    local_day = datetime.now(AUTOMATION_TIMEZONE).strftime("%y%m%d")
    return f"BUG-{local_day}-{secrets.token_hex(2).upper()}"


def save_bug_report(username, category, description, conversation_id=""):
    report = {
        "id": _new_bug_ticket_id(),
        "username": username,
        "category": str(category or "Autre")[:60],
        "description": str(description or "").strip()[:2000],
        "conversation_id": str(conversation_id or "")[:100],
        "device": request_device_label(),
        "created_at": utc_now(),
        "status": "new",
    }
    if supabase_accounts_enabled():
        try:
            supabase_request(
                "POST",
                SUPABASE_BUG_REPORTS_TABLE,
                report,
                {"Prefer": "return=minimal"},
            )
            return _decorate_bug_report(report)
        except RuntimeError:
            pass

    reports = load_local_json(BUG_REPORTS_FILE, [])
    if not isinstance(reports, list):
        reports = []
    reports.append(report)
    atomic_write_json(BUG_REPORTS_FILE, reports[-1000:])
    return _decorate_bug_report(report)


def update_bug_report_status(report_id, status):
    status = str(status or "").strip()
    if status not in BUG_STATUS_LABELS:
        raise ValueError("Statut de ticket invalide.")

    updated = False
    if supabase_accounts_enabled():
        try:
            result = supabase_request(
                "PATCH",
                (
                    f"{SUPABASE_BUG_REPORTS_TABLE}"
                    f"?id=eq.{quote(str(report_id), safe='')}"
                ),
                {"status": status},
                {"Prefer": "return=representation"},
            ) or []
            updated = bool(result)
        except RuntimeError:
            pass

    local_reports = load_local_json(BUG_REPORTS_FILE, [])
    if isinstance(local_reports, list):
        local_changed = False
        for item in local_reports:
            if isinstance(item, dict) and str(item.get("id")) == str(report_id):
                item["status"] = status
                local_changed = True
                updated = True
                break
        if local_changed:
            atomic_write_json(BUG_REPORTS_FILE, local_reports[-1000:])

    return updated



def create_conversation_share(username, conversation, hours=24):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=hours)).isoformat()
    record = {
        "token": token,
        "username": username,
        "conversation_id": str(conversation.get("id") or "")[:100],
        "title": str(conversation.get("title") or "Conversation")[:120],
        "snapshot": conversation,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
    }
    if supabase_accounts_enabled():
        try:
            supabase_request(
                "POST",
                SUPABASE_SHARES_TABLE,
                record,
                {"Prefer": "return=minimal"},
            )
            return record
        except RuntimeError:
            pass
    shares = load_local_json(SHARE_LINKS_FILE, {})
    if not isinstance(shares, dict):
        shares = {}
    shares[token] = record
    atomic_write_json(SHARE_LINKS_FILE, shares)
    return record


def get_conversation_share(token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{30,80}", str(token or "")):
        return None
    record = None
    if supabase_accounts_enabled():
        try:
            rows = supabase_request(
                "GET",
                f"{SUPABASE_SHARES_TABLE}?token=eq.{quote(token, safe='')}&select=token,username,conversation_id,title,snapshot,created_at,expires_at&limit=1",
            ) or []
            if rows:
                record = rows[0]
        except RuntimeError:
            pass
    if record is None:
        shares = load_local_json(SHARE_LINKS_FILE, {})
        if isinstance(shares, dict):
            record = shares.get(token)
    if not isinstance(record, dict):
        return None
    try:
        expires = datetime.fromisoformat(str(record.get("expires_at") or ""))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return None
    except (TypeError, ValueError):
        return None
    return record



def list_conversation_shares(username, include_expired=False):
    records = []
    if supabase_accounts_enabled():
        try:
            rows = supabase_request(
                "GET",
                f"{SUPABASE_SHARES_TABLE}?username=eq.{quote(username, safe='')}&select=token,conversation_id,title,created_at,expires_at&order=created_at.desc",
            ) or []
            records = [row for row in rows if isinstance(row, dict)]
        except RuntimeError:
            pass

    if not records:
        shares = load_local_json(SHARE_LINKS_FILE, {})
        if isinstance(shares, dict):
            records = [
                item for item in shares.values()
                if isinstance(item, dict) and str(item.get("username", "")).casefold() == username.casefold()
            ]
            records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    now = datetime.now(timezone.utc)
    output = []
    for record in records:
        expired = False
        try:
            expires = datetime.fromisoformat(str(record.get("expires_at") or ""))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            expired = expires <= now
        except (TypeError, ValueError):
            expired = True
        if expired and not include_expired:
            continue
        clean = dict(record)
        clean["expired"] = expired
        output.append(clean)
    return output


def revoke_conversation_share(username, token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{30,80}", str(token or "")):
        return False

    removed = False
    if supabase_accounts_enabled():
        try:
            rows = supabase_request(
                "GET",
                f"{SUPABASE_SHARES_TABLE}?token=eq.{quote(token, safe='')}&username=eq.{quote(username, safe='')}&select=token&limit=1",
            ) or []
            if rows:
                supabase_request(
                    "DELETE",
                    f"{SUPABASE_SHARES_TABLE}?token=eq.{quote(token, safe='')}&username=eq.{quote(username, safe='')}",
                    extra_headers={"Prefer": "return=minimal"},
                )
                removed = True
        except RuntimeError:
            pass

    shares = load_local_json(SHARE_LINKS_FILE, {})
    if isinstance(shares, dict):
        record = shares.get(token)
        if isinstance(record, dict) and str(record.get("username", "")).casefold() == username.casefold():
            shares.pop(token, None)
            atomic_write_json(SHARE_LINKS_FILE, shares)
            removed = True
    return removed


def user_statistics(username):
    conversations = load_json(CONVERSATIONS_FILE, {})
    owner = next((key for key in conversations if key.casefold() == username.casefold()), username)
    items = conversations.get(owner, [])
    if not isinstance(items, list):
        items = []

    stats = {
        "conversations": len(items),
        "pinned": sum(1 for item in items if isinstance(item, dict) and item.get("pinned")),
        "messages": 0,
        "questions": 0,
        "answers": 0,
        "images": 0,
        "cricut_images": 0,
        "first_message_at": None,
        "last_message_at": None,
    }
    dates = []
    for conversation in items:
        if not isinstance(conversation, dict):
            continue
        for message in conversation.get("messages", []) or []:
            if not isinstance(message, dict):
                continue
            stats["messages"] += 1
            if message.get("role") == "user":
                stats["questions"] += 1
            elif message.get("role") == "assistant":
                stats["answers"] += 1
            if message.get("image_url"):
                stats["images"] += 1
            stats["cricut_images"] += len(message.get("cricut_images", []) or [])
            created_at = str(message.get("created_at") or "")
            if created_at:
                dates.append(created_at)
    if dates:
        dates.sort()
        stats["first_message_at"] = dates[0]
        stats["last_message_at"] = dates[-1]
    stats["total_generations"] = stats["images"] + stats["cricut_images"]
    stats["active_shares"] = len(list_conversation_shares(username))
    return stats


def _average_generation_seconds_from_conversations(conversations, sample_limit=250):
    durations = []
    for items in conversations.values():
        if not isinstance(items, list):
            continue
        for conversation in items:
            if not isinstance(conversation, dict):
                continue
            pending_user_at = None
            for message in conversation.get("messages", []) or []:
                if not isinstance(message, dict):
                    continue
                created = _parse_iso_datetime(message.get("created_at"))
                if not created:
                    continue
                role = message.get("role")
                if role == "user":
                    pending_user_at = created
                    continue
                if role == "assistant" and pending_user_at:
                    seconds = (created - pending_user_at).total_seconds()
                    if 0 <= seconds <= 2 * 60 * 60:
                        durations.append((created, seconds))
                    pending_user_at = None

    durations.sort(key=lambda item: item[0], reverse=True)
    values = [seconds for _, seconds in durations[:max(1, int(sample_limit))]]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _format_duration_short(seconds):
    seconds = max(0, int(round(float(seconds or 0))))
    if not seconds:
        return "—"
    if seconds < 60:
        return f"{seconds} s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {remainder:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d}"


def build_staff_statistics():
    users = load_json(USERS_FILE, {})
    conversations = load_json(CONVERSATIONS_FILE, {})
    now = datetime.now(timezone.utc)
    day_keys = [(now - timedelta(days=offset)).date().isoformat() for offset in range(13, -1, -1)]
    daily = {key: {"date": key, "questions": 0, "answers": 0, "images": 0, "cricut": 0} for key in day_keys}
    top_users = []
    total_questions = total_answers = total_images = total_cricut = 0

    for username, items in conversations.items():
        if not isinstance(items, list):
            continue
        user_message_count = 0
        user_generations = 0
        for conversation in items:
            if not isinstance(conversation, dict):
                continue
            for message in conversation.get("messages", []) or []:
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                if role == "user":
                    total_questions += 1
                    user_message_count += 1
                elif role == "assistant":
                    total_answers += 1
                image_count = 1 if message.get("image_url") else 0
                cricut_count = len(message.get("cricut_images", []) or [])
                total_images += image_count
                total_cricut += cricut_count
                user_generations += image_count + cricut_count

                date_key = ""
                try:
                    created = datetime.fromisoformat(str(message.get("created_at") or ""))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    date_key = created.astimezone(AUTOMATION_TIMEZONE).date().isoformat()
                except (TypeError, ValueError):
                    pass
                if date_key in daily:
                    if role == "user":
                        daily[date_key]["questions"] += 1
                    elif role == "assistant":
                        daily[date_key]["answers"] += 1
                    daily[date_key]["images"] += image_count
                    daily[date_key]["cricut"] += cricut_count
        top_users.append({
            "username": username,
            "questions": user_message_count,
            "generations": user_generations,
            "conversations": len(items),
        })

    top_users.sort(key=lambda item: (item["questions"], item["generations"]), reverse=True)
    active_24h = 0
    for details in users.values():
        if not isinstance(details, dict):
            continue
        last_seen = details.get("last_seen_at") or details.get("last_login_at")
        if not last_seen:
            continue
        try:
            seen = datetime.fromisoformat(str(last_seen))
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if (now - seen.astimezone(timezone.utc)).total_seconds() <= 86400:
                active_24h += 1
        except (TypeError, ValueError):
            pass

    runtime = discord_bridge.runtime_metrics()
    average_generation_seconds = _average_generation_seconds_from_conversations(conversations)
    return {
        "accounts": len(users),
        "active_24h": active_24h,
        "conversations": sum(len(items) for items in conversations.values() if isinstance(items, list)),
        "questions": total_questions,
        "answers": total_answers,
        "images": total_images,
        "cricut": total_cricut,
        "queue_waiting": int(runtime.get("queue_waiting", 0) or 0),
        "active_jobs": int(runtime.get("active_jobs", 0) or 0),
        "average_generation_seconds": average_generation_seconds,
        "average_generation_label": _format_duration_short(average_generation_seconds),
        "recent_errors_24h": count_recent_runtime_errors(24),
        "daily": [daily[key] for key in day_keys],
        "top_users": top_users[:12],
    }


def delete_conversation(username, conversation_id):
    conversations = load_json(CONVERSATIONS_FILE, {})
    owner_key = next(
        (key for key in conversations if key.casefold() == username.casefold()),
        None,
    )
    if owner_key:
        conversations[owner_key] = [
            item for item in conversations[owner_key]
            if item.get("id") != conversation_id
        ]
        if not conversations[owner_key]:
            conversations.pop(owner_key, None)
        save_json(CONVERSATIONS_FILE, conversations)


def is_cricut_conversation(conversation):
    """Les discussions Cricut restent conservées malgré le nettoyage quotidien."""
    if not isinstance(conversation, dict):
        return False
    if str(conversation.get("id", "")).startswith("cricut-"):
        return True
    return any(
        isinstance(message, dict) and message.get("cricut_images")
        for message in conversation.get("messages", [])
    )


def delete_all_non_cricut_conversations():
    """Efface l'historique ordinaire de chaque compte sans toucher à Cricut."""
    conversations = load_json(CONVERSATIONS_FILE, {})
    if not isinstance(conversations, dict):
        return 0

    deleted_count = 0
    changed = False
    for username in list(conversations):
        items = conversations.get(username, [])
        if not isinstance(items, list):
            continue
        kept_items = [item for item in items if is_cricut_conversation(item)]
        deleted_count += len(items) - len(kept_items)
        if len(kept_items) != len(items):
            changed = True
        if kept_items:
            conversations[username] = kept_items
        else:
            conversations.pop(username, None)

    if changed:
        save_json(CONVERSATIONS_FILE, conversations)
    return deleted_count


def get_automatic_generations(username):
    all_generations = load_json(AUTOMATIC_GENERATIONS_FILE, {})
    if not isinstance(all_generations, dict):
        return []
    owner_key = next(
        (key for key in all_generations if key.casefold() == username.casefold()),
        None,
    )
    items = all_generations.get(owner_key, []) if owner_key else []
    if not isinstance(items, list):
        return []
    return list(reversed(items))


def save_automatic_generation(username, generation):
    all_generations = load_json(AUTOMATIC_GENERATIONS_FILE, {})
    if not isinstance(all_generations, dict):
        all_generations = {}

    owner_key = next(
        (key for key in all_generations if key.casefold() == username.casefold()),
        username,
    )
    items = all_generations.setdefault(owner_key, [])
    generation_id = str(generation.get("id", ""))
    existing = next(
        (item for item in items if item.get("id") == generation_id),
        None,
    )
    if existing is None:
        items.append(generation)
    else:
        existing.update(generation)

    # Une année complète est largement suffisante et garde le disque léger.
    all_generations[owner_key] = items[-366:]
    save_json(AUTOMATIC_GENERATIONS_FILE, all_generations)


def mark_automatic_generation_opened(username, generation_id):
    all_generations = load_json(AUTOMATIC_GENERATIONS_FILE, {})
    if not isinstance(all_generations, dict):
        return False
    owner_key = next(
        (key for key in all_generations if key.casefold() == username.casefold()),
        None,
    )
    if not owner_key:
        return False
    for item in all_generations.get(owner_key, []):
        if item.get("id") == generation_id:
            if not item.get("opened_at"):
                item["opened_at"] = utc_now()
                save_json(AUTOMATIC_GENERATIONS_FILE, all_generations)
            return True
    return False


AUTOMATIC_STICKER_THEMES = (
    ("football", "Football : ballon, maillot, trophée, sifflet, terrain et supporters"),
    ("cinema", "Cinéma et séries : clap, popcorn, caméra, tickets et étoiles"),
    ("voyage", "Voyage : valise, avion, carte, appareil photo et soleil"),
    ("musique", "Musique : casque, vinyle, guitare, micro et notes colorées"),
    ("gaming", "Jeux vidéo : manette, console rétro, joystick, trophée et pixels"),
    ("nature", "Nature : fleurs, feuilles, champignons, papillons et arc-en-ciel"),
    ("gourmand", "Gourmandises : pâtisseries, fraises, café, glace et petits gâteaux"),
)


def daily_theme_for(date_value, previous_theme_id=""):
    """Choisit un thème saisonnier ou populaire sans répétition consécutive."""
    month_day = (date_value.month, date_value.day)
    seasonal = None
    if month_day == (1, 1):
        seasonal = ("nouvel-an", "Nouvel An : confettis, feux d'artifice, chiffres de l'année et cotillons")
    elif date_value.month == 2 and 8 <= date_value.day <= 16:
        seasonal = ("saint-valentin", "Saint-Valentin : coeurs, fleurs, lettres d'amour et rubans")
    elif date_value.month in {3, 4}:
        seasonal = ("printemps", "Printemps : fleurs, pluie douce, abeilles, pousses et jardin")
    elif date_value.month == 10:
        seasonal = ("halloween", "Halloween : citrouilles, fantômes mignons, bonbons, chauves-souris et lunes")
    elif date_value.month == 12:
        seasonal = ("hiver", "Fêtes d'hiver : flocons, cadeaux, chocolat chaud, étoiles et sapins")

    if seasonal and seasonal[0] != previous_theme_id:
        return seasonal

    index = date_value.toordinal() % len(AUTOMATIC_STICKER_THEMES)
    theme = AUTOMATIC_STICKER_THEMES[index]
    if theme[0] == previous_theme_id:
        theme = AUTOMATIC_STICKER_THEMES[(index + 1) % len(AUTOMATIC_STICKER_THEMES)]
    return theme


def automatic_sheet_prompt(theme_label):
    return (
        "Génère une planche de stickers style scrapbooking, prête à découper, "
        "sur fond blanc propre. Thème du jour : " + theme_label + ". "
        "Compose 12 illustrations distinctes, couleurs vives, contours très fins, "
        "sans texte, sans watermark et avec chaque sticker bien séparé."
    )


def download_automatic_source_image(image_url):
    """Télécharge l'image générée afin de l'envoyer au flux Cricut."""
    parsed = urlparse(str(image_url or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("URL d'image automatique invalide.")
    request_object = Request(
        image_url,
        headers={"User-Agent": "NathGPT automation"},
    )
    with urlopen(request_object, timeout=45) as response:
        content_type = str(response.headers.get("Content-Type", "")).lower()
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024 or not data:
        raise ValueError("L'image automatique est trop grande ou vide.")
    if content_type and not content_type.startswith("image/"):
        raise ValueError("Le résultat automatique n'est pas une image.")
    return data


def is_image_generation_request(question, has_reference_images=False):
    """DÃ©termine cÃ´tÃ© serveur si le rÃ©sultat attendu est une image."""
    if has_reference_images:
        return True

    text = unicodedata.normalize("NFD", str(question or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))

    if text.startswith("modify:") or text == "png:":
        return True

    keywords = (
        "genere une image", "genere l'image", "genere image",
        "cree une image", "creer une image", "cree l'image", "creer l'image",
        "fais une image", "fait une image", "dessine", "genere une photo",
        "cree une photo", "creer une photo", "genere une illustration",
        "cree une illustration", "creer une illustration", "image de", "photo de",
        "illustration de", "generate an image", "create an image",
        "generate a picture", "create a picture", "draw me",
    )
    return any(keyword in text for keyword in keywords)


def get_reference_images():

    images = request.files.getlist("reference_images")

    if len(images) > 4:
        raise ValueError("Tu peux envoyer jusqu'à 4 images de référence.")

    result = []

    for image in images:
        if not image or not image.filename:
            continue

        filename = secure_filename(image.filename)
        extension = Path(filename).suffix.lower()

        if extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise ValueError("Les références doivent être des images PNG, JPG, WEBP ou GIF.")

        data = image.read(8 * 1024 * 1024 + 1)

        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Chaque image de référence est limitée à 8 Mo.")

        result.append({
            "filename": filename,
            "data": data,
        })

    return result


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _maintenance_datetime_local(value):
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return ""
    return parsed.astimezone(AUTOMATION_TIMEZONE).strftime("%Y-%m-%dT%H:%M")


def get_feature_maintenance_state():
    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}

    raw_features = state.get("features")
    if not isinstance(raw_features, dict):
        raw_features = {}

    now = datetime.now(timezone.utc)
    features = {}
    for key, meta in FEATURE_MAINTENANCE_DEFAULTS.items():
        raw_feature = raw_features.get(key, {})
        if not isinstance(raw_feature, dict):
            raw_feature = {}

        manual_enabled = raw_feature.get("enabled")
        if manual_enabled is None:
            manual_enabled = True

        scheduled_start = _parse_iso_datetime(raw_feature.get("scheduled_start"))
        scheduled_end = _parse_iso_datetime(raw_feature.get("scheduled_end"))
        scheduled_active = bool(
            scheduled_start
            and scheduled_end
            and scheduled_start <= now < scheduled_end
        )
        schedule_pending = bool(scheduled_start and scheduled_end and now < scheduled_start)
        schedule_finished = bool(scheduled_end and now >= scheduled_end)
        enabled = bool(manual_enabled) and not scheduled_active

        manual_reason = str(raw_feature.get("maintenance_reason") or "").strip()
        scheduled_reason = str(raw_feature.get("scheduled_reason") or "").strip()
        active_reason = (
            scheduled_reason or meta["default_reason"]
            if scheduled_active
            else manual_reason
        )

        features[key] = {
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "enabled": enabled,
            "manual_enabled": bool(manual_enabled),
            "maintenance_reason": active_reason,
            "manual_maintenance_reason": manual_reason,
            "default_reason": meta["default_reason"],
            "updated_at": raw_feature.get("updated_at") or None,
            "updated_by": raw_feature.get("updated_by") or None,
            "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
            "scheduled_end": scheduled_end.isoformat() if scheduled_end else None,
            "scheduled_start_local": _maintenance_datetime_local(scheduled_start.isoformat()) if scheduled_start else "",
            "scheduled_end_local": _maintenance_datetime_local(scheduled_end.isoformat()) if scheduled_end else "",
            "scheduled_reason": scheduled_reason,
            "scheduled_active": scheduled_active,
            "schedule_pending": schedule_pending,
            "schedule_finished": schedule_finished,
        }

    return features

def is_feature_enabled(feature_key):
    feature = get_feature_maintenance_state().get(feature_key)
    if not feature:
        return True
    return bool(feature.get("enabled"))


def set_feature_enabled(feature_key, enabled, reason="", updated_by="staff"):
    if feature_key not in FEATURE_MAINTENANCE_DEFAULTS:
        raise KeyError(feature_key)

    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}

    features = state.get("features")
    if not isinstance(features, dict):
        features = {}
        state["features"] = features

    feature_state = features.get(feature_key)
    if not isinstance(feature_state, dict):
        feature_state = {}
        features[feature_key] = feature_state

    feature_state["enabled"] = bool(enabled)
    feature_state["updated_at"] = utc_now()
    feature_state["updated_by"] = str(updated_by or "staff")[:60]

    if enabled:
        feature_state.pop("maintenance_reason", None)
    else:
        cleaned_reason = " ".join(str(reason or "").split())[:180]
        feature_state["maintenance_reason"] = (
            cleaned_reason
            or FEATURE_MAINTENANCE_DEFAULTS[feature_key]["default_reason"]
        )

    save_json(SERVICE_STATUS_FILE, state)
    return get_feature_maintenance_state()[feature_key]


def set_feature_schedule(feature_key, start_local, end_local, reason="", updated_by="staff"):
    if feature_key not in FEATURE_MAINTENANCE_DEFAULTS:
        raise KeyError(feature_key)

    try:
        start_dt = datetime.strptime(start_local, "%Y-%m-%dT%H:%M").replace(tzinfo=AUTOMATION_TIMEZONE)
        end_dt = datetime.strptime(end_local, "%Y-%m-%dT%H:%M").replace(tzinfo=AUTOMATION_TIMEZONE)
    except (TypeError, ValueError) as error:
        raise ValueError("Dates de maintenance invalides.") from error

    if end_dt <= start_dt:
        raise ValueError("La fin de maintenance doit être après le début.")

    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}
    features = state.setdefault("features", {})
    feature_state = features.setdefault(feature_key, {})
    feature_state["scheduled_start"] = start_dt.astimezone(timezone.utc).isoformat()
    feature_state["scheduled_end"] = end_dt.astimezone(timezone.utc).isoformat()
    feature_state["scheduled_reason"] = (
        " ".join(str(reason or "").split())[:180]
        or FEATURE_MAINTENANCE_DEFAULTS[feature_key]["default_reason"]
    )
    feature_state["updated_at"] = utc_now()
    feature_state["updated_by"] = str(updated_by or "staff")[:60]
    save_json(SERVICE_STATUS_FILE, state)
    return get_feature_maintenance_state()[feature_key]


def clear_feature_schedule(feature_key, updated_by="staff"):
    if feature_key not in FEATURE_MAINTENANCE_DEFAULTS:
        raise KeyError(feature_key)
    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}
    features = state.setdefault("features", {})
    feature_state = features.setdefault(feature_key, {})
    for field in ("scheduled_start", "scheduled_end", "scheduled_reason"):
        feature_state.pop(field, None)
    feature_state["updated_at"] = utc_now()
    feature_state["updated_by"] = str(updated_by or "staff")[:60]
    save_json(SERVICE_STATUS_FILE, state)
    return get_feature_maintenance_state()[feature_key]


def feature_maintenance_response(feature_key, status_code=503):
    feature = get_feature_maintenance_state().get(feature_key)
    if not feature:
        return jsonify({
            "error": "Cette fonctionnalité est temporairement indisponible.",
        }), status_code

    message = feature["maintenance_reason"] or feature["default_reason"]
    return jsonify({
        "error": message,
        "feature_maintenance": feature,
    }), status_code


def _append_runtime_error_event(state, error_code, source="service"):
    events = state.get("recent_errors")
    if not isinstance(events, list):
        events = []

    now = datetime.now(timezone.utc)
    code = str(error_code or "API-503")[:80]
    should_append = True
    if events:
        last = events[-1] if isinstance(events[-1], dict) else {}
        last_at = _parse_iso_datetime(last.get("created_at"))
        if (
            str(last.get("code") or "") == code
            and last_at
            and (now - last_at).total_seconds() < 10
        ):
            should_append = False

    if should_append:
        events.append({
            "created_at": now.isoformat(),
            "code": code,
            "source": str(source or "service")[:60],
        })

    cutoff = now - timedelta(days=7)
    kept = []
    for item in events[-400:]:
        if not isinstance(item, dict):
            continue
        created = _parse_iso_datetime(item.get("created_at"))
        if created and created >= cutoff:
            kept.append(item)
    state["recent_errors"] = kept[-250:]


def count_recent_runtime_errors(hours=24):
    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        return 0
    events = state.get("recent_errors")
    if not isinstance(events, list):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    count = 0
    for item in events:
        if not isinstance(item, dict):
            continue
        created = _parse_iso_datetime(item.get("created_at"))
        if created and created >= cutoff:
            count += 1
    return count


def get_service_status():
    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}

    # Discord limite une catégorie à 50 salons. Dès que le staff en libère un,
    # la vérification périodique du site réactive NathGPT sans redeploy.
    if (
        state.get("outage")
        and state.get("error_code") == "API-SALONS-PLEINS"
        and discord_bridge.category_has_capacity()
    ):
        state["outage"] = False
        state["resolved_at"] = utc_now()
        save_json(SERVICE_STATUS_FILE, state)

    return {
        "outage": bool(state.get("outage")),
        "error_code": str(state.get("error_code") or "API-503")[:40],
        "started_at": state.get("started_at") or None,
        "staff_notified_at": state.get("staff_notified_at") or None,
        "features": get_feature_maintenance_state(),
    }


def set_service_outage(error_code="API-503"):
    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}
    if not state.get("outage"):
        state["started_at"] = utc_now()
        state.pop("staff_notified_at", None)
    state["outage"] = True
    state["error_code"] = str(error_code or "API-503")[:40]
    _append_runtime_error_event(state, state["error_code"], source="generation")
    save_json(SERVICE_STATUS_FILE, state)
    return get_service_status()


def clear_service_outage():
    state = load_json(SERVICE_STATUS_FILE, {})
    if not isinstance(state, dict) or not state.get("outage"):
        return
    state["outage"] = False
    state["resolved_at"] = utc_now()
    save_json(SERVICE_STATUS_FILE, state)


def handle_discord_connection_change(connected):
    if connected:
        clear_service_outage()
    else:
        set_service_outage("API-DISCORD")


def service_outage_response(status_code=503):
    state = get_service_status()
    return jsonify({
        "error": f"NathGPT est hors ligne · erreur {state['error_code']}.",
        "outage": state,
    }), status_code


def outage_code_for_error(error):
    """Ne redémarre pas le bot pour une limite Discord qui n'est pas réseau."""
    details = str(error or "").casefold()
    if (
        "maximum number of channels in category" in details
        or "maximum number of channels" in details
    ):
        return "API-SALONS-PLEINS"
    return "API-DISCORD"


def web_push_configuration_errors():
    """Retourne des erreurs sûres à afficher au staff, sans exposer de clé."""
    errors = []
    if not VAPID_SUBJECT:
        errors.append("VAPID_SUBJECT est manquant.")
    elif VAPID_SUBJECT.startswith("mailto:"):
        email = VAPID_SUBJECT.removeprefix("mailto:")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append("VAPID_SUBJECT contient une adresse e-mail invalide.")
    else:
        subject_url = urlparse(VAPID_SUBJECT)
        if subject_url.scheme != "https" or not subject_url.netloc:
            errors.append("VAPID_SUBJECT doit être un mailto: valide ou une URL https:// valide.")

    if not VAPID_PUBLIC_KEY:
        errors.append("VAPID_PUBLIC_KEY est manquante.")
    else:
        try:
            padded_key = VAPID_PUBLIC_KEY + "=" * (-len(VAPID_PUBLIC_KEY) % 4)
            public_key_bytes = base64.urlsafe_b64decode(padded_key.encode("ascii"))
            if len(public_key_bytes) != 65 or public_key_bytes[0] != 4:
                raise ValueError("format")
        except Exception:
            errors.append("VAPID_PUBLIC_KEY est invalide.")

    if not VAPID_PRIVATE_KEY:
        errors.append("VAPID_PRIVATE_KEY est manquante.")
    return errors


def web_push_is_configured():
    """Indique si l'envoi de notifications Web Push est prêt côté serveur."""
    return not web_push_configuration_errors()


def send_web_push_notification(username, title, body, conversation_id=None):
    """Avertit tous les appareils abonnés et retourne un bilan sans secrets."""
    report = {
        "sent": 0,
        "expired": 0,
        "failed": 0,
        "subscriptions": 0,
        "errors": web_push_configuration_errors(),
    }
    if report["errors"]:
        return report

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        # Le site et Discord restent disponibles même si le déploiement n'a
        # pas encore installé la dépendance de notifications.
        app.logger.warning("Notifications Web Push indisponibles : pywebpush manque.")
        report["errors"].append("La bibliothèque pywebpush est indisponible sur le serveur.")
        return report

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        return report

    subscriptions = users[user_key].get("web_push_subscriptions", [])
    if not isinstance(subscriptions, list):
        return report

    payload = json.dumps({
        "title": str(title)[:120],
        "body": str(body)[:240],
        "url": "/chat",
        "conversation_id": str(conversation_id or "")[:100],
    }, ensure_ascii=False)
    valid_subscriptions = []
    changed = False

    for subscription in subscriptions:
        if not isinstance(subscription, dict) or not subscription.get("endpoint"):
            changed = True
            continue
        report["subscriptions"] += 1

        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            valid_subscriptions.append(subscription)
            report["sent"] += 1
        except WebPushException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            # Une souscription expirée ne doit pas empêcher les autres
            # appareils de recevoir leur notification.
            if status in {404, 410}:
                changed = True
                report["expired"] += 1
                continue
            valid_subscriptions.append(subscription)
            report["failed"] += 1
            if status in {401, 403}:
                report["errors"].append(
                    "Le service Push a refusé l'authentification VAPID (clé privée ou subject à vérifier)."
                )
            elif status == 400:
                report["errors"].append(
                    "Le service Push a refusé une souscription ou la configuration VAPID."
                )
            else:
                report["errors"].append(
                    f"Le service Push a refusé une livraison (HTTP {status or 'inconnu'})."
                )
            app.logger.warning("Notification Web Push non envoyée : %s", error)
        except Exception:
            valid_subscriptions.append(subscription)
            report["failed"] += 1
            report["errors"].append("Erreur technique lors de l'envoi d'une notification.")
            app.logger.exception("Erreur pendant l'envoi d'une notification Web Push")

    if changed:
        users[user_key]["web_push_subscriptions"] = valid_subscriptions
        save_json(USERS_FILE, users)

    report["errors"] = list(dict.fromkeys(report["errors"]))
    return report


def send_web_push_broadcast(title, body):
    """Envoie une notification staff à tous les comptes et agrège le résultat."""
    configuration_errors = web_push_configuration_errors()
    users = load_json(USERS_FILE, {})
    report = {
        "accounts": len(users) if isinstance(users, dict) else 0,
        "subscribed_accounts": 0,
        "subscriptions": 0,
        "sent": 0,
        "expired": 0,
        "failed": 0,
        "errors": list(configuration_errors),
    }
    if configuration_errors or not isinstance(users, dict):
        return report

    try:
        import pywebpush  # noqa: F401
    except ImportError:
        report["errors"].append("La bibliothèque pywebpush est indisponible sur le serveur.")
        return report

    for username, details in users.items():
        subscriptions = details.get("web_push_subscriptions", []) if isinstance(details, dict) else []
        if isinstance(subscriptions, list) and any(
            isinstance(subscription, dict) and subscription.get("endpoint")
            for subscription in subscriptions
        ):
            report["subscribed_accounts"] += 1
        user_report = send_web_push_notification(username, title, body)
        for key in ("subscriptions", "sent", "expired", "failed"):
            report[key] += int(user_report.get(key, 0) or 0)
        report["errors"].extend(user_report.get("errors", []))

    report["errors"] = list(dict.fromkeys(report["errors"]))
    return report


def start_automatic_cricut_from_image(username, image_url, metadata):
    """Enchaîne la découpe Cricut sans bloquer la boucle Discord."""
    try:
        source_data = download_automatic_source_image(image_url)
        automatic_date = str(metadata.get("automatic_date", ""))
        source_image = {
            "filename": f"planche-scrapbooking-{automatic_date or 'du-jour'}.png",
            "data": source_data,
        }
        cricut_metadata = {
            "automation": "daily-cricut",
            "automatic_date": automatic_date,
            "theme_id": str(metadata.get("theme_id", "")),
            "theme_label": str(metadata.get("theme_label", "")),
            "source_image_url": str(image_url),
        }
        automatic_conversation_id = (
            "cricut-auto-"
            + hashlib.sha256(username.casefold().encode("utf-8")).hexdigest()[:12]
        )
        discord_bridge.start_cricut_job(
            username,
            source_image,
            cricut_metadata,
            conversation_id=automatic_conversation_id,
            reuse_channel=True,
        )
    except Exception:
        app.logger.exception("Impossible de lancer la découpe Cricut automatique")
        send_web_push_notification(
            username,
            "La génération automatique a besoin d'aide",
            "La planche a été créée, mais son adaptation Cricut n'a pas démarré.",
        )


def save_daily_automatic_generation(username, event):
    metadata = event.get("_job_metadata", {})
    automatic_date = str(metadata.get("automatic_date", ""))
    images = [
        str(url)[:2000]
        for url in event.get("images", [])
        if str(url).strip()
    ][:300]
    if not automatic_date or not images:
        return
    save_automatic_generation(username, {
        "id": f"auto-{automatic_date}",
        "date": automatic_date,
        "title": f"Planche automatique · {metadata.get('theme_label', 'Scrapbooking')}",
        "theme_id": str(metadata.get("theme_id", "")),
        "theme_label": str(metadata.get("theme_label", "")),
        "source_image_url": str(metadata.get("source_image_url", ""))[:2000],
        "images": images,
        "created_at": utc_now(),
        "opened_at": None,
    })


def save_discord_result(username, conversation_id, event):

    metadata = event.get("_job_metadata", {})

    if event.get("type") == "image":
        save_conversation_message(
            username,
            conversation_id,
            "assistant",
            "Image générée",
            event.get("url")
        )
        send_web_push_notification(
            username,
            "Ton image est prête",
            "NathGPT a terminé ta génération.",
            conversation_id,
        )
        if metadata.get("automation") == "daily-sheet":
            worker = threading.Thread(
                target=start_automatic_cricut_from_image,
                args=(username, event.get("url", ""), metadata),
                name="nathgpt-auto-cricut",
                daemon=True,
            )
            worker.start()

    elif event.get("type") == "text":
        save_conversation_message(
            username,
            conversation_id,
            "assistant",
            event.get("message", "")
        )
        send_web_push_notification(
            username,
            "NathGPT a répondu",
            str(event.get("message", "Une nouvelle réponse est disponible."))[:220],
            conversation_id,
        )

    elif event.get("type") == "cricut_complete":
        images = event.get("images", [])
        save_conversation_message(
            username,
            conversation_id,
            "assistant",
            f"Stickers Cricut terminés · {len(images)} image(s) prête(s) à télécharger.",
            cricut_images=images,
        )
        send_web_push_notification(
            username,
            "Tes stickers Cricut sont prêts",
            f"{len(images)} image(s) sont prêtes à télécharger.",
            conversation_id,
        )
        if metadata.get("automation") == "daily-cricut":
            save_daily_automatic_generation(username, event)

    elif event.get("type") == "error":
        set_service_outage("API-DISCORD")
        # Une réponse finale en erreur peut venir d'un bot bloqué sans avoir
        # déclenché l'évènement de déconnexion Discord : on force alors une
        # connexion neuve pour sortir automatiquement du mode maintenance.
        discord_bridge.request_reconnect("erreur finale reçue")


discord_bridge.set_result_handler(
    save_discord_result
)
discord_bridge.set_connection_handler(
    handle_discord_connection_change
)


# ============================================================
# AUTOMATISATIONS QUOTIDIENNES
# ============================================================

_automation_thread = None
_automation_thread_lock = threading.Lock()


def load_automation_state():
    state = load_json(AUTOMATION_STATE_FILE, {})
    return state if isinstance(state, dict) else {}


def save_automation_state(state):
    save_json(AUTOMATION_STATE_FILE, state)


def run_midnight_cleanup(date_key):
    """Supprime l'historique ordinaire et les salons Discord non Cricut."""
    state = load_automation_state()
    day_state = state.setdefault("days", {}).setdefault(date_key, {})
    if day_state.get("cleanup_completed"):
        return

    deleted_history = delete_all_non_cricut_conversations()
    try:
        deleted_channels = discord_bridge.delete_non_cricut_category_channels()
    except RuntimeError:
        # Le nettoyage local a déjà eu lieu. On réessaiera les salons Discord
        # au prochain passage tant que le bot n'est pas reconnecté.
        app.logger.exception("Nettoyage quotidien Discord reporté")
        return

    day_state["cleanup_completed"] = True
    day_state["cleanup_at"] = utc_now()
    day_state["deleted_history"] = deleted_history
    day_state["deleted_discord_channels"] = deleted_channels
    save_automation_state(state)


def start_daily_automatic_generations(date_value):
    """Lance une planche puis sa découpe Cricut pour chaque compte éligible."""
    date_key = date_value.isoformat()
    state = load_automation_state()
    day_state = state.setdefault("days", {}).setdefault(date_key, {})
    if day_state.get("automation_skipped_on_first_start"):
        return
    previous_theme_id = str(state.get("last_theme_id", ""))
    theme_id = str(day_state.get("theme_id", ""))
    theme_label = str(day_state.get("theme_label", ""))
    if not theme_id or not theme_label:
        theme_id, theme_label = daily_theme_for(date_value, previous_theme_id)
        day_state["theme_id"] = theme_id
        day_state["theme_label"] = theme_label

    started_users = set(day_state.get("started_users", []))
    users = load_json(USERS_FILE, {})
    if not isinstance(users, dict):
        return

    for username, details in users.items():
        if not isinstance(details, dict) or not details.get("cricut_enabled"):
            continue
        if username.casefold() in started_users:
            continue

        safe_user = hashlib.sha256(username.casefold().encode("utf-8")).hexdigest()[:12]
        conversation_id = f"auto-{date_value.strftime('%Y%m%d')}-{safe_user}"
        metadata = {
            "automation": "daily-sheet",
            "automatic_date": date_key,
            "theme_id": theme_id,
            "theme_label": theme_label,
        }
        try:
            save_conversation_message(
                username,
                conversation_id,
                "user",
                f"Planche automatique du {date_value.strftime('%d/%m/%Y')} · {theme_label}",
            )
            discord_bridge.start_turn(
                username,
                conversation_id,
                automatic_sheet_prompt(theme_label),
                expects_image=True,
                metadata=metadata,
            )
        except Exception:
            app.logger.exception("Impossible de lancer la génération automatique pour %s", username)
            continue

        started_users.add(username.casefold())
        day_state["started_users"] = sorted(started_users)
        day_state["started_at"] = utc_now()
        state["last_theme_id"] = theme_id
        save_automation_state(state)


def automation_loop():
    """Rattrape un redémarrage puis déclenche minuit et 01:00, heure de Paris."""
    while True:
        try:
            now = datetime.now(AUTOMATION_TIMEZONE)
            date_value = now.date()
            date_key = date_value.isoformat()
            state = load_automation_state()
            if not state.get("scheduler_initialized"):
                # Au premier déploiement, on attend le prochain minuit plutôt
                # que d'effacer l'historique en plein milieu de journée.
                state["scheduler_initialized"] = True
                state.setdefault("days", {}).setdefault(date_key, {})["cleanup_completed"] = True
                state["days"][date_key]["cleanup_at"] = utc_now()
                if now.hour >= 1:
                    state["days"][date_key]["automation_skipped_on_first_start"] = True
                save_automation_state(state)
            day_state = state.get("days", {}).get(date_key, {}) if isinstance(state.get("days"), dict) else {}

            if not day_state.get("cleanup_completed"):
                run_midnight_cleanup(date_key)
            if now.hour >= 1:
                start_daily_automatic_generations(date_value)
        except Exception:
            app.logger.exception("Erreur dans l'automatisation quotidienne")

        # Une vérification toutes les 30 secondes permet de rattraper un
        # redémarrage sans dériver de l'heure de Paris.
        time.sleep(30)


def start_automation_service():
    global _automation_thread
    if not AUTOMATION_ENABLED:
        return
    with _automation_thread_lock:
        if _automation_thread and _automation_thread.is_alive():
            return
        _automation_thread = threading.Thread(
            target=automation_loop,
            name="nathgpt-daily-automation",
            daemon=True,
        )
        _automation_thread.start()


# ============================================================
# CLE SECRETE FLASK
# ============================================================

def get_or_create_secret():

    configured_secret = os.environ.get(
        "NATHGPT_SECRET_KEY",
        ""
    ).strip()

    if configured_secret:
        return configured_secret

    if SECRET_FILE.exists():

        value = SECRET_FILE.read_text(
            encoding="utf-8"
        ).strip()

        if value:

            return value


    value = secrets.token_hex(32)


    SECRET_FILE.write_text(
        value,
        encoding="utf-8"
    )


    return value


app.secret_key = get_or_create_secret()


# ============================================================
# CONFIG SESSION
# ============================================================

app.config.update(

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SAMESITE="Lax",

    # Mets True plus tard si ton site utilise HTTPS
    SESSION_COOKIE_SECURE=(
        os.environ.get(
            "SESSION_COOKIE_SECURE",
            "false"
        ).lower() == "true"
    ),

)


_runtime_services_lock = threading.Lock()
_runtime_services_started = False


def start_runtime_services():
    """Start Discord only after Gunicorn has exposed the HTTP application."""
    global _runtime_services_started

    if _runtime_services_started:
        return

    with _runtime_services_lock:
        if _runtime_services_started:
            return

        _runtime_services_started = True
        if os.environ.get(
            "DISCORD_AUTOSTART",
            "true"
        ).lower() == "true":
            discord_bridge.start()
        start_automation_service()


# Gunicorn importe ce module au démarrage : le bot se lance également
# en production, avec un seul worker configuré dans render.yaml.
@app.before_request
def boot_runtime_services_after_http_startup():
    """The first Render health check starts the bot without blocking Flask."""
    start_runtime_services()


# ============================================================
# RECUPERER IP UTILISATEUR
# ============================================================

def client_ip():

    forwarded = request.headers.get(
        "X-Forwarded-For",
        ""
    )


    if forwarded:

        return forwarded.split(",")[0].strip()


    return request.remote_addr or "unknown"


# ============================================================
# USERNAME
# ============================================================

def normalize_username(username: str):

    return username.strip()


def valid_username(username: str):

    return (
        re.fullmatch(
            r"[A-Za-z0-9_.-]{3,24}",
            username
        )
        is not None
    )


# ============================================================
# TOKEN
# ============================================================

def hash_token(raw_token: str):

    return hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()


# ============================================================
# TROUVER USER SANS TENIR COMPTE DES MAJUSCULES
# ============================================================

def find_user_key(users, username):

    wanted = username.casefold()


    for key in users:

        if key.casefold() == wanted:

            return key


    return None


# ============================================================
# APPAREIL ET CONNEXION DU COMPTE
# ============================================================

def request_device_label():
    """Produit un libellé lisible sans conserver l'empreinte complète du navigateur."""
    user_agent = request.headers.get("User-Agent", "")
    text = user_agent.casefold()

    if "iphone" in text:
        match = re.search(r"os ([\d_]+)", text)
        system = f"iOS {match.group(1).replace('_', '.')}" if match else "iOS"
        device = f"Apple iPhone · {system}"
    elif "ipad" in text:
        match = re.search(r"os ([\d_]+)", text)
        system = f"iPadOS {match.group(1).replace('_', '.')}" if match else "iPadOS"
        device = f"Apple iPad · {system}"
    elif "android" in text:
        match = re.search(r"android\s+([\d.]+)", text)
        system = f"Android {match.group(1)}" if match else "Android"
        device = system
    elif "windows" in text:
        device = "Windows"
    elif "mac os x" in text or "macintosh" in text:
        device = "Apple Mac"
    elif "linux" in text:
        device = "Linux"
    else:
        device = "Appareil inconnu"

    if "edg/" in text or "edga/" in text:
        browser = "Microsoft Edge"
    elif "firefox/" in text:
        browser = "Firefox"
    elif "opr/" in text or "opera" in text:
        browser = "Opera"
    elif "chrome/" in text or "crios/" in text:
        browser = "Chrome"
    elif "safari/" in text:
        browser = "Safari"
    else:
        browser = "Navigateur"

    return f"{device} · {browser}"[:120]


def record_last_device(user):
    user["last_device"] = request_device_label()
    user["last_device_seen_at"] = utc_now()

def add_ip_to_user(
    users,
    username,
    ip
):

    user = users[username]


    known_ips = user.setdefault(
        "known_ips",
        []
    )


    if (
        ip
        and ip != "unknown"
        and ip not in known_ips
    ):

        known_ips.append(ip)


    user["last_ip"] = ip

    user["last_login_at"] = utc_now()
    record_last_device(user)


# ============================================================
# ACTIVITE DES COMPTES (sans identifier le materiel)
# ============================================================

def touch_user_activity(username):
    """Met Ã  jour l'activitÃ© rÃ©cente, au plus une fois par minute."""
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    last_write = int(session.get("_activity_written_at", 0) or 0)

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)

    if not user_key:
        return

    current_device = request_device_label()
    if now_timestamp - last_write < 60 and users[user_key].get("last_device") == current_device:
        return

    users[user_key]["last_seen_at"] = utc_now()
    users[user_key]["last_device"] = current_device
    users[user_key]["last_device_seen_at"] = utc_now()
    save_json(USERS_FILE, users)
    session["_activity_written_at"] = now_timestamp


def staff_account_summaries():
    """PrÃ©pare des donnÃ©es minimales pour le panneau staff."""
    users = load_json(USERS_FILE, {})
    now = datetime.now(timezone.utc)
    accounts = []

    for username, details in users.items():
        last_seen = details.get("last_seen_at") or details.get("last_login_at")
        active = False

        if last_seen:
            try:
                seen_at = datetime.fromisoformat(last_seen)
                active = (now - seen_at).total_seconds() <= STAFF_ACTIVE_WINDOW_SECONDS
            except (TypeError, ValueError):
                pass

        accounts.append({
            "username": username,
            "created_at": details.get("created_at", "Inconnue"),
            "last_seen_at": last_seen or "Jamais",
            "last_device": details.get("last_device", "Inconnu"),
            "active": active,
            "banned_until": get_ban_expiration(details),
            "access_status": (
                "trial"
                if details.get("access_status") == "trial" and is_user_access_allowed(details)
                else "expired"
                if details.get("access_status") == "trial"
                else "permanent"
            ),
            "trial_expires_at": get_trial_access_expiration(details),
        })

    accounts.sort(key=lambda account: (not account["active"], account["username"].casefold()))
    return accounts


def get_ban_expiration(user):
    """Retourne la fin du bannissement si le compte est encore banni."""
    value = user.get("banned_until")
    if not value:
        return None

    try:
        expiration = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    return expiration if expiration > datetime.now(timezone.utc) else None


def is_user_banned(user):
    return get_ban_expiration(user) is not None


def get_trial_access_expiration(user):
    """Retourne la date de fin d'essai, y compris lorsqu'elle est dépassée."""
    if user.get("access_status") != "trial":
        return None

    value = user.get("trial_expires_at")
    try:
        expiration = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=timezone.utc)
    return expiration


def is_user_access_allowed(user):
    """Les comptes historiques restent permanents ; seuls les essais expirent."""
    if user.get("access_status") != "trial":
        return True

    expiration = get_trial_access_expiration(user)
    return bool(expiration and expiration > datetime.now(timezone.utc))


def access_unavailable_message(user):
    if user.get("access_status") == "trial":
        return (
            "Votre accès d'essai de 1 jour est terminé. "
            "Un membre du staff doit valider votre accès permanent."
        )
    return "Ce compte est temporairement indisponible."


def revoke_user_tokens(username):
    """Invalide les cookies de connexion persistante d'un compte."""
    tokens = load_json(TOKENS_FILE, {})
    wanted = username.casefold()
    filtered = {
        token_hash: details
        for token_hash, details in tokens.items()
        if str(details.get("username", "")).casefold() != wanted
    }

    if len(filtered) != len(tokens):
        save_json(TOKENS_FILE, filtered)


def remove_user_account(username):
    """Supprime le compte et ses donnÃ©es locales aprÃ¨s effacement Discord."""
    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        return False

    # Cette Ã©tape peut lever une erreur : dans ce cas le compte local reste
    # intact, pour respecter la promesse de suppression Ã©galement sur Discord.
    discord_bridge.delete_user_conversations(user_key)

    del users[user_key]
    save_json(USERS_FILE, users)
    revoke_user_tokens(user_key)

    conversations = load_json(CONVERSATIONS_FILE, {})
    for conversation_owner in list(conversations):
        if conversation_owner.casefold() == user_key.casefold():
            del conversations[conversation_owner]
    save_json(CONVERSATIONS_FILE, conversations)
    return True


def handle_discord_staff_account_action(username, action):
    """Exécute l'action confirmée par le bouton du message privé staff."""
    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        return "Ce compte n'existe plus."

    if action == "grant-permanent-access":
        users[user_key]["access_status"] = "permanent"
        users[user_key].pop("trial_expires_at", None)
        users[user_key]["access_granted_at"] = utc_now()
        save_json(USERS_FILE, users)
        return f"Accès permanent accordé à {user_key}."

    if action == "delete":
        try:
            remove_user_account(user_key)
        except RuntimeError as error:
            return f"Suppression impossible pour {user_key} : {error}"
        return f"Le compte {user_key} a été supprimé."

    return "Action de compte inconnue."


discord_bridge.set_account_action_handler(handle_discord_staff_account_action)


def remove_all_user_conversations(username):
    """Efface les discussions d'un compte, y compris leurs salons Discord."""
    # Comme pour la suppression du compte, ne pas supprimer la copie locale
    # tant que Discord n'a pas confirmé la suppression de ses salons.
    discord_bridge.delete_user_conversations(username)

    conversations = load_json(CONVERSATIONS_FILE, {})
    owner_key = next(
        (key for key in conversations if key.casefold() == username.casefold()),
        None,
    )
    count = len(conversations.get(owner_key, [])) if owner_key else 0
    if owner_key:
        del conversations[owner_key]
        save_json(CONVERSATIONS_FILE, conversations)
    return count


def staff_dashboard_stats(accounts):
    """Calcule des statistiques globales sans exposer de données sensibles."""
    conversations = load_json(CONVERSATIONS_FILE, {})
    conversation_count = 0
    message_count = 0
    generated_image_count = 0

    for items in conversations.values():
        if not isinstance(items, list):
            continue
        conversation_count += len(items)
        for conversation in items:
            messages = conversation.get("messages", []) if isinstance(conversation, dict) else []
            if not isinstance(messages, list):
                continue
            message_count += len(messages)
            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("image_url"):
                    generated_image_count += 1
                generated_image_count += len(message.get("cricut_images", []) or [])

    return {
        "accounts": len(accounts),
        "active": sum(account["active"] for account in accounts),
        "banned": sum(bool(account["banned_until"]) for account in accounts),
        "cricut_accounts": sum(
            1 for details in load_json(USERS_FILE, {}).values()
            if details.get("cricut_enabled")
        ),
        "conversations": conversation_count,
        "messages": message_count,
        "images": generated_image_count,
    }


def staff_is_authenticated():
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    return bool(STAFF_PASSWORD) and int(
        session.get("staff_access_until", 0) or 0
    ) > now_timestamp


def get_staff_csrf_token():
    token = session.get("staff_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["staff_csrf_token"] = token
    return token


def get_settings_csrf_token():
    token = session.get("settings_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["settings_csrf_token"] = token
    return token


def render_staff_dashboard(
    temporary_password=None,
    temporary_username=None,
    notification_report=None,
):
    accounts = staff_account_summaries()
    return render_template(
        "staff.html",
        authenticated=True,
        accounts=accounts,
        stats=staff_dashboard_stats(accounts),
        active_window_minutes=STAFF_ACTIVE_WINDOW_SECONDS // 60,
        staff_csrf_token=get_staff_csrf_token(),
        discord_category_id=discord_bridge.category_id,
        feature_states=list(get_feature_maintenance_state().values()),
        bug_reports=get_staff_bug_reports(),
        bug_statuses=BUG_STATUS_LABELS,
        temporary_password=temporary_password,
        temporary_username=temporary_username,
        notification_report=notification_report,
    )


# ============================================================
# CREER TOKEN DE CONNEXION
# ============================================================

def create_remember_token(
    username,
    ip
):

    raw_token = secrets.token_urlsafe(48)


    token_hash = hash_token(
        raw_token
    )


    tokens = load_json(
        TOKENS_FILE,
        {}
    )


    tokens[token_hash] = {

        "username":
            username,

        "created_at":
            utc_now(),

        "last_seen_at":
            utc_now(),

        "last_ip":
            ip,

    }


    save_json(
        TOKENS_FILE,
        tokens
    )


    return raw_token


# ============================================================
# REVOQUER TOKEN
# ============================================================

def revoke_token(raw_token):

    if not raw_token:

        return


    tokens = load_json(
        TOKENS_FILE,
        {}
    )


    token_hash = hash_token(
        raw_token
    )


    if token_hash in tokens:

        del tokens[token_hash]


        save_json(
            TOKENS_FILE,
            tokens
        )


# ============================================================
# SESSION CONNECTEE
# ============================================================

def set_login_session(username):

    session.clear()


    session["username"] = username


    session.permanent = True


# ============================================================
# COOKIE AUTOMATIQUE
# ============================================================

def response_with_remember_cookie(
    response,
    username,
    ip
):

    raw_token = create_remember_token(
        username,
        ip
    )


    response.set_cookie(

        REMEMBER_COOKIE_NAME,

        raw_token,

        max_age=
            REMEMBER_DAYS
            * 24
            * 60
            * 60,

        httponly=True,

        # Mets True quand ton site est en HTTPS
        secure=False,

        samesite="Lax",

    )


    return response


# ============================================================
# AUTO LOGIN COOKIE
# ============================================================

def try_cookie_autologin():

    raw_token = request.cookies.get(
        REMEMBER_COOKIE_NAME
    )


    if not raw_token:

        return None


    tokens = load_json(
        TOKENS_FILE,
        {}
    )


    token_hash = hash_token(
        raw_token
    )


    token_info = tokens.get(
        token_hash
    )


    if not token_info:

        return None


    users = load_json(
        USERS_FILE,
        {}
    )


    username = token_info.get(
        "username"
    )


    user_key = find_user_key(
        users,
        username or ""
    )


    if not user_key:

        return None

    if is_user_banned(users[user_key]) or not is_user_access_allowed(users[user_key]):
        return None


    ip = client_ip()


    add_ip_to_user(
        users,
        user_key,
        ip
    )


    save_json(
        USERS_FILE,
        users
    )


    token_info["last_seen_at"] = utc_now()

    token_info["last_ip"] = ip


    tokens[token_hash] = token_info


    save_json(
        TOKENS_FILE,
        tokens
    )


    set_login_session(
        user_key
    )


    return user_key


# ============================================================
# AUTO LOGIN PAR IP
# ============================================================

def try_ip_autologin():

    if not ALLOW_IP_AUTOLOGIN:

        return None


    ip = client_ip()


    if (
        not ip
        or ip == "unknown"
    ):

        return None


    users = load_json(
        USERS_FILE,
        {}
    )


    matches = []


    for username, info in users.items():

        known_ips = info.get(
            "known_ips",
            []
        )


        if ip in known_ips and not is_user_banned(info) and is_user_access_allowed(info):

            matches.append(
                username
            )


    # On reconnecte uniquement si cette IP
    # correspond à UN SEUL compte.

    if len(matches) != 1:

        return None


    username = matches[0]


    add_ip_to_user(
        users,
        username,
        ip
    )


    save_json(
        USERS_FILE,
        users
    )


    set_login_session(
        username
    )


    return username


# ============================================================
# AUTO LOGIN AVANT CHAQUE PAGE
# ============================================================

@app.before_request
def automatic_login():

    # Pas besoin pour les fichiers CSS etc.

    if request.endpoint == "static":

        return


    if session.get("username"):
        users = load_json(USERS_FILE, {})
        user_key = find_user_key(users, session["username"])

        if not user_key or is_user_banned(users[user_key]) or not is_user_access_allowed(users[user_key]):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": access_unavailable_message(users.get(user_key, {}))}), 403
            flash(access_unavailable_message(users.get(user_key, {})), "error")
            return redirect(url_for("login"))

        touch_user_activity(session["username"])
        return


    # Ne pas reconnecter automatiquement
    # quand quelqu'un veut créer un compte
    # ou se déconnecter.

    if request.endpoint in {
        "register",
        "logout"
    }:

        return


    # Cookie en priorité

    if try_cookie_autologin():

        return


    # IP ensuite

    try_ip_autologin()


# ============================================================
# LOGO
# ============================================================

@app.route("/logo.png")
def logo():
    response = send_from_directory(BASE_DIR, "logo.png", mimetype="image/png")
    # Le paramètre ?v=<empreinte> rend chaque nouveau logo unique.
    # On peut donc le mettre longtemps en cache sans conserver une ancienne version.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.route("/api/logo-version")
def logo_version_api():
    """Permet au front/PWA de détecter automatiquement un logo remplacé."""
    return jsonify({
        "version": current_logo_version(),
        "url": f"/logo.png?v={current_logo_version()}",
    })


@app.route("/favicon.ico")
def favicon():

    return send_from_directory(
        BASE_DIR,
        "logo.png",
        mimetype="image/png"
    )


@app.route("/manifest.webmanifest")
def dynamic_manifest():
    """Manifest PWA dont l'icône suit automatiquement le contenu de logo.png."""
    version = current_logo_version()
    manifest = {
        "name": "NathGPT",
        "short_name": "NathGPT",
        "description": "Création d'images et adaptation de stickers avec NathGPT.",
        "lang": "fr",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "background_color": "#1c2422",
        "theme_color": "#1c2422",
        "icons": [{
            "src": f"/logo.png?v={version}",
            "sizes": "800x800",
            "type": "image/png",
            "purpose": "any maskable",
        }],
    }
    response = jsonify(manifest)
    response.headers["Content-Type"] = "application/manifest+json"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/service-worker.js")
def service_worker():
    """Worker dynamique : changer logo.png suffit à changer sa version et son cache."""
    version = current_logo_version()
    source = (BASE_DIR / "static" / "service-worker.js").read_text(encoding="utf-8")
    source = source.replace("__LOGO_VERSION__", version)
    response = make_response(source)
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/api/notifications/config")
def notification_config():
    """Expose uniquement la clé publique nécessaire à l'abonnement du navigateur."""
    if not session.get("username"):
        return jsonify({"error": "Connexion requise."}), 401

    return jsonify({
        "enabled": web_push_is_configured(),
        "public_key": VAPID_PUBLIC_KEY if web_push_is_configured() else "",
    })


@app.route("/api/notifications/subscribe", methods=["POST"])
def subscribe_to_notifications():
    """Enregistre un appareil pour les alertes de fin de génération."""
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    if not web_push_is_configured():
        return jsonify({"error": "Les notifications push ne sont pas encore configurées."}), 503

    subscription = request.get_json(silent=True)
    endpoint = str((subscription or {}).get("endpoint", "")).strip()
    keys = (subscription or {}).get("keys")
    if not endpoint.startswith("https://") or not isinstance(keys, dict):
        return jsonify({"error": "Abonnement de notification invalide."}), 400

    clean_subscription = {
        "endpoint": endpoint[:2000],
        "expirationTime": (subscription or {}).get("expirationTime"),
        "keys": {
            "p256dh": str(keys.get("p256dh", ""))[:500],
            "auth": str(keys.get("auth", ""))[:500],
        },
    }
    if not clean_subscription["keys"]["p256dh"] or not clean_subscription["keys"]["auth"]:
        return jsonify({"error": "Clés de notification invalides."}), 400

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        return jsonify({"error": "Compte introuvable."}), 404

    subscriptions = users[user_key].setdefault("web_push_subscriptions", [])
    if not isinstance(subscriptions, list):
        subscriptions = []
        users[user_key]["web_push_subscriptions"] = subscriptions

    subscriptions[:] = [
        item for item in subscriptions
        if isinstance(item, dict) and item.get("endpoint") != clean_subscription["endpoint"]
    ]
    subscriptions.append(clean_subscription)
    users[user_key]["web_push_subscriptions"] = subscriptions[-10:]
    save_json(USERS_FILE, users)

    return jsonify({"ok": True})


@app.route("/health")
def health():

    return {"status": "ok"}, 200


@app.route("/api/service-status")
def service_status():
    if not session.get("username"):
        return jsonify({"error": "Connexion requise."}), 401
    return jsonify(get_service_status())


@app.route("/api/service-outage/notify-staff", methods=["POST"])
def notify_staff_about_outage():
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    state = get_service_status()
    if not state["outage"]:
        return jsonify({"error": "NathGPT est de nouveau disponible."}), 409

    now = datetime.now(timezone.utc)
    previous_notification = state.get("staff_notified_at")
    if previous_notification:
        try:
            previous_time = datetime.fromisoformat(previous_notification)
            remaining = OUTAGE_STAFF_NOTIFICATION_COOLDOWN_SECONDS - int(
                (now - previous_time).total_seconds()
            )
            if remaining > 0:
                return jsonify({
                    "queued": True,
                    "message": "Le staff a déjà été averti récemment."
                })
        except (TypeError, ValueError):
            pass

    try:
        discord_bridge.notify_staff_waiting(username)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503

    saved_state = load_json(SERVICE_STATUS_FILE, {})
    saved_state["staff_notified_at"] = utc_now()
    save_json(SERVICE_STATUS_FILE, saved_state)
    return jsonify({
        "queued": True,
        "message": "Le staff a été averti que tu attends."
    })


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if session.get("username"):

        return redirect(
            url_for("chat")
        )


    return redirect(
        url_for("login")
    )


# ============================================================
# CAPTCHA SIMPLE D'INSCRIPTION
# ============================================================

def new_registration_captcha():
    left = secrets.randbelow(8) + 2
    right = secrets.randbelow(8) + 1
    session["registration_captcha_answer"] = str(left + right)
    session["registration_captcha_question"] = f"{left} + {right}"
    return session["registration_captcha_question"]


def registration_captcha_question():
    return session.get("registration_captcha_question") or new_registration_captcha()


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=[
        "GET",
        "POST"
    ]
)
def register():

    if session.get("username"):

        return redirect(
            url_for("chat")
        )


    if request.method == "POST":

        username = normalize_username(
            request.form.get(
                "username",
                ""
            )
        )


        password = request.form.get(
            "password",
            ""
        )


        password2 = request.form.get(
            "password2",
            ""
        )

        captcha_answer = str(request.form.get("captcha_answer", "")).strip()
        expected_captcha = str(session.get("registration_captcha_answer", ""))
        if not expected_captcha or not secrets.compare_digest(captcha_answer, expected_captcha):
            flash("Captcha incorrect. Résous le nouveau calcul pour continuer.", "error")
            new_registration_captcha()
            return render_template("register.html", captcha_question=registration_captcha_question())

        # Un captcha validé ne peut pas être réutilisé lors d'une seconde requête.
        session.pop("registration_captcha_answer", None)
        session.pop("registration_captcha_question", None)


        # Validation pseudo

        if not valid_username(
            username
        ):

            flash(
                (
                    "Le pseudo doit contenir entre "
                    "3 et 24 caractères : "
                    "lettres, chiffres, _, . ou -."
                ),
                "error"
            )


            new_registration_captcha()
            return render_template(
                "register.html",
                captcha_question=registration_captcha_question(),
            )


        # Validation mot de passe

        if len(password) < 8:

            flash(
                (
                    "Le mot de passe doit contenir "
                    "au moins 8 caractères."
                ),
                "error"
            )


            new_registration_captcha()
            return render_template(
                "register.html",
                captcha_question=registration_captcha_question(),
            )


        # Password confirmation

        if password != password2:

            flash(
                (
                    "Les deux mots de passe "
                    "ne correspondent pas."
                ),
                "error"
            )


            new_registration_captcha()
            return render_template(
                "register.html",
                captcha_question=registration_captcha_question(),
            )


        users = load_json(
            USERS_FILE,
            {}
        )


        # Vérifie pseudo existant

        if find_user_key(
            users,
            username
        ):

            flash(
                "Ce pseudo existe déjà.",
                "error"
            )


            new_registration_captcha()
            return render_template(
                "register.html",
                captcha_question=registration_captcha_question(),
            )


        ip = client_ip()


        # Création utilisateur

        users[username] = {

            "password_hash":
                generate_password_hash(
                    password
                ),

            "created_at":
                utc_now(),

            "access_status": "trial",

            "trial_expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=TRIAL_ACCESS_HOURS)
            ).isoformat(),

            "last_login_at":
                utc_now(),

            "last_device":
                request_device_label(),

            "last_device_seen_at":
                utc_now(),

            "last_ip":
                ip,

            "known_ips":
                (
                    [ip]
                    if ip != "unknown"
                    else []
                ),

        }


        save_json(
            USERS_FILE,
            users
        )


        # Connexion immédiate

        set_login_session(
            username
        )

        session["registration_notice"] = (
            "Vous avez accès 1 jour à NathGPT en attendant la validation "
            "d'un membre du staff pour votre accès permanent."
        )

        try:
            discord_bridge.notify_staff_new_account(username)
        except RuntimeError as error:
            app.logger.warning("Alerte staff de nouveau compte non envoyée : %s", error)


        response = make_response(

            redirect(
                url_for("chat")
            )

        )


        return response_with_remember_cookie(

            response,
            username,
            ip

        )


    new_registration_captcha()
    return render_template(
        "register.html",
        captcha_question=registration_captcha_question(),
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=[
        "GET",
        "POST"
    ]
)
def login():

    if session.get("username"):

        return redirect(
            url_for("chat")
        )


    if request.method == "POST":

        username = normalize_username(
            request.form.get(
                "username",
                ""
            )
        )


        password = request.form.get(
            "password",
            ""
        )


        users = load_json(
            USERS_FILE,
            {}
        )


        user_key = find_user_key(
            users,
            username
        )


        if not user_key:

            flash(
                "Pseudo ou mot de passe incorrect.",
                "error"
            )


            return render_template(
                "login.html"
            )


        user = users[
            user_key
        ]


        if is_user_banned(user) or not is_user_access_allowed(user):
            flash(
                access_unavailable_message(user),
                "error"
            )
            return render_template("login.html")


        # Vérifie mot de passe

        if not check_password_hash(

            user.get(
                "password_hash",
                ""
            ),

            password

        ):

            flash(
                "Pseudo ou mot de passe incorrect.",
                "error"
            )


            return render_template(
                "login.html"
            )


        ip = client_ip()


        add_ip_to_user(
            users,
            user_key,
            ip
        )


        save_json(
            USERS_FILE,
            users
        )


        set_login_session(
            user_key
        )


        response = make_response(

            redirect(
                url_for("chat")
            )

        )


        return response_with_remember_cookie(

            response,
            user_key,
            ip

        )


    return render_template(
        "login.html"
    )


# ============================================================
# CHAT
# ============================================================

@app.route("/chat")
def chat():

    username = session.get(
        "username"
    )


    if not username:

        return redirect(
            url_for("login")
        )


    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)

    return render_template(

        "chat.html",

        username=username,
        cricut_enabled=bool(user_key and users[user_key].get("cricut_enabled")),
        app_release=APP_RELEASE,
        pending_releases=get_pending_releases(users.get(user_key, {}) if user_key else {}),
        staff_impersonating=bool(session.get("staff_impersonating")),
        registration_notice=session.pop("registration_notice", None),
        user_theme=(users.get(user_key, {}).get("theme") if user_key else None) or "nathgpt",
        theme_color=THEME_OPTIONS.get((users.get(user_key, {}).get("theme") if user_key else None) or "nathgpt", THEME_OPTIONS["nathgpt"])["color"],
        battery_saver=bool(user_key and users[user_key].get("battery_saver")),

    )


# ============================================================
# PARAMETRES DU COMPTE
# ============================================================

@app.route("/settings")
def settings():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "settings.html",
        username=user_key,
        account=users[user_key],
        settings_csrf_token=get_settings_csrf_token(),
        theme_options=THEME_OPTIONS,
        active_shares=list_conversation_shares(user_key),
        user_theme=users[user_key].get("theme") or "nathgpt",
        theme_color=THEME_OPTIONS.get(users[user_key].get("theme") or "nathgpt", THEME_OPTIONS["nathgpt"])["color"],
        battery_saver=bool(users[user_key].get("battery_saver")),
    )


@app.route("/settings/preferences", methods=["POST"])
def update_preferences():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("settings_csrf_token", "")):
        return "Requête invalide.", 400

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        session.clear()
        return redirect(url_for("login"))

    theme = str(request.form.get("theme") or "nathgpt").strip().lower()
    if theme not in THEME_OPTIONS:
        theme = "nathgpt"
    users[user_key]["theme"] = theme
    users[user_key]["battery_saver"] = request.form.get("battery_saver") == "1"
    users[user_key]["preferences_updated_at"] = utc_now()
    save_json(USERS_FILE, users)
    flash("Préférences enregistrées.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/shares/<token>/revoke", methods=["POST"])
def revoke_share(token):
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))
    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("settings_csrf_token", "")):
        return "Requête invalide.", 400
    if revoke_conversation_share(username, token):
        flash("Lien de partage révoqué. Il n'est plus accessible.", "success")
    else:
        flash("Ce lien est déjà expiré ou introuvable.", "error")
    return redirect(url_for("settings"))


@app.route("/settings/generations")
def generation_history_page():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        session.clear()
        return redirect(url_for("login"))

    theme = users[user_key].get("theme") or "nathgpt"
    return render_template(
        "generation_history.html",
        username=user_key,
        generation_items=flatten_generation_history(user_key),
        user_theme=theme,
        theme_color=THEME_OPTIONS.get(theme, THEME_OPTIONS["nathgpt"])["color"],
        battery_saver=bool(users[user_key].get("battery_saver")),
    )


@app.route("/stats")
@app.route("/settings/stats")
def my_statistics():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))
    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        session.clear()
        return redirect(url_for("login"))
    theme = users[user_key].get("theme") or "nathgpt"
    return render_template(
        "stats.html",
        username=user_key,
        stats=user_statistics(user_key),
        account=users[user_key],
        user_theme=theme,
        theme_color=THEME_OPTIONS.get(theme, THEME_OPTIONS["nathgpt"])["color"],
        battery_saver=bool(users[user_key].get("battery_saver")),
    )


@app.route("/settings/delete-account", methods=["POST"])
def delete_own_account():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("settings_csrf_token", "")):
        return "RequÃªte de suppression invalide.", 400

    confirmation = request.form.get("confirmation", "").strip()
    password = request.form.get("password", "")
    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)

    if not user_key:
        session.clear()
        return redirect(url_for("login"))

    if confirmation != "SUPPRIMER MON COMPTE" or not check_password_hash(
        users[user_key].get("password_hash", ""), password
    ):
        flash("La confirmation ou le mot de passe est incorrect.", "error")
        return redirect(url_for("settings"))

    try:
        remove_user_account(user_key)
    except RuntimeError as error:
        flash(str(error), "error")
        return redirect(url_for("settings"))

    session.clear()
    response = make_response(redirect(url_for("login")))
    response.delete_cookie(REMEMBER_COOKIE_NAME, path="/")
    flash("Ton compte, tes conversations et tes salons Discord ont Ã©tÃ© supprimÃ©s.", "success")
    return response


# ============================================================
# PANNEAU STAFF
# ============================================================

@app.route("/staff", methods=["GET", "POST"])
def staff_panel():
    """Panneau staff protÃ©gÃ© par STAFF_PASSWORD (variable Render)."""
    if not STAFF_PASSWORD:
        return "Le panneau staff n'est pas configurÃ©.", 503

    now_timestamp = int(datetime.now(timezone.utc).timestamp())

    if request.method == "POST":
        lock_until = int(session.get("staff_lock_until", 0) or 0)
        supplied_password = request.form.get("password", "")

        if now_timestamp < lock_until:
            flash("Trop de tentatives. RÃ©essaie dans quelques minutes.", "error")
        elif secrets.compare_digest(supplied_password, STAFF_PASSWORD):
            session.pop("staff_attempts", None)
            session.pop("staff_lock_until", None)
            session["staff_access_until"] = now_timestamp + STAFF_SESSION_SECONDS
            return redirect(url_for("staff_panel"))
        else:
            attempts = int(session.get("staff_attempts", 0) or 0) + 1
            session["staff_attempts"] = attempts

            if attempts >= 5:
                session["staff_attempts"] = 0
                session["staff_lock_until"] = now_timestamp + 10 * 60
                flash("Trop de tentatives. RÃ©essaie dans 10 minutes.", "error")
            else:
                flash("Mot de passe incorrect.", "error")

    access_until = int(session.get("staff_access_until", 0) or 0)

    if access_until <= now_timestamp:
        session.pop("staff_access_until", None)
        return render_template("staff.html", authenticated=False)

    return render_staff_dashboard()


@app.route("/staff/statistics")
def staff_statistics():
    if not staff_is_authenticated():
        return redirect(url_for("staff_panel"))
    return render_template(
        "staff_stats.html",
        stats=build_staff_statistics(),
    )


@app.route("/api/staff/runtime-stats")
def staff_runtime_stats():
    if not staff_is_authenticated():
        return jsonify({"error": "Accès staff requis."}), 403
    runtime = discord_bridge.runtime_metrics()
    runtime["recent_errors_24h"] = count_recent_runtime_errors(24)
    return jsonify(runtime)


@app.route("/staff/notifications/broadcast", methods=["POST"])
def staff_broadcast_notification():
    if not staff_is_authenticated():
        return "Accès staff requis.", 403

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400

    if request.form.get("confirmation", "").strip() != "NOTIFIER TOUS":
        flash("Écris NOTIFIER TOUS pour confirmer l'envoi global.", "error")
        return redirect(url_for("staff_panel"))

    title = " ".join(request.form.get("title", "").split())[:120]
    body = " ".join(request.form.get("body", "").split())[:240]
    if not title or not body:
        flash("Le titre et le message de la notification sont obligatoires.", "error")
        return redirect(url_for("staff_panel"))

    report = send_web_push_broadcast(title, body)
    return render_staff_dashboard(notification_report=report)


@app.route("/staff/features/<feature_key>/toggle", methods=["POST"])
def staff_feature_toggle(feature_key):
    if not staff_is_authenticated():
        return "Accès staff requis.", 403

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400

    if feature_key not in FEATURE_MAINTENANCE_DEFAULTS:
        return "Fonctionnalité inconnue.", 404

    raw_enabled = str(request.form.get("enabled", "")).strip().lower()
    enable_feature = raw_enabled in {"1", "true", "yes", "on"}
    reason = request.form.get("maintenance_reason", "")

    feature_state = set_feature_enabled(
        feature_key,
        enable_feature,
        reason=reason,
        updated_by=session.get("username") or "staff",
    )

    if feature_state["enabled"]:
        flash(f"{feature_state['label']} est de nouveau disponible.", "success")
    else:
        flash(f"{feature_state['label']} passe en maintenance ciblée.", "success")

    return redirect(url_for("staff_panel"))


@app.route("/staff/accounts/<username>/impersonate", methods=["POST"])
def staff_impersonate_account(username):
    if not staff_is_authenticated():
        return "Accès staff requis.", 403
    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400
    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        flash("Compte introuvable.", "error")
        return redirect(url_for("staff_panel"))
    session["staff_impersonating"] = True
    session["staff_impersonated_username"] = user_key
    session["username"] = user_key
    session.permanent = True
    return redirect(url_for("chat"))


@app.route("/staff/stop-impersonation", methods=["POST"])
def staff_stop_impersonation():
    if not staff_is_authenticated() or not session.get("staff_impersonating"):
        return redirect(url_for("chat"))
    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400
    session.pop("staff_impersonating", None)
    session.pop("staff_impersonated_username", None)
    session.pop("username", None)
    return redirect(url_for("staff_panel"))


@app.route("/staff/features/<feature_key>/schedule", methods=["POST"])
def staff_feature_schedule(feature_key):
    if not staff_is_authenticated():
        return "Accès staff requis.", 403

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400

    if feature_key not in FEATURE_MAINTENANCE_DEFAULTS:
        return "Fonctionnalité inconnue.", 404

    action = request.form.get("schedule_action", "save").strip().lower()
    try:
        if action == "clear":
            feature = clear_feature_schedule(feature_key, session.get("username") or "staff")
            flash(f"Maintenance programmée supprimée pour {feature['label']}.", "success")
        else:
            feature = set_feature_schedule(
                feature_key,
                request.form.get("scheduled_start", ""),
                request.form.get("scheduled_end", ""),
                request.form.get("scheduled_reason", ""),
                session.get("username") or "staff",
            )
            flash(f"Maintenance programmée enregistrée pour {feature['label']}.", "success")
    except ValueError as error:
        flash(str(error), "error")

    return redirect(url_for("staff_panel"))


@app.route("/staff/bugs/<report_id>/status", methods=["POST"])
def staff_bug_status(report_id):
    if not staff_is_authenticated():
        return "Accès staff requis.", 403

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400

    status = request.form.get("status", "")
    try:
        updated = update_bug_report_status(report_id, status)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("staff_panel"))

    if not updated:
        flash("Ticket de bug introuvable.", "error")
    else:
        flash(
            f"Ticket {report_id} → {BUG_STATUS_LABELS.get(status, status)}.",
            "success",
        )
    return redirect(url_for("staff_panel"))


@app.route("/staff/accounts/<username>/<action>", methods=["POST"])
def staff_account_action(username, action):
    """Actions sensibles disponibles uniquement au staff authentifiÃ©."""
    if not staff_is_authenticated():
        return "AccÃ¨s staff requis.", 403

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "RequÃªte staff invalide.", 400

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        flash("Compte introuvable.", "error")
        return redirect(url_for("staff_panel"))

    if action == "grant-permanent-access":
        users[user_key]["access_status"] = "permanent"
        users[user_key].pop("trial_expires_at", None)
        users[user_key]["access_granted_at"] = utc_now()
        save_json(USERS_FILE, users)
        flash(f"Accès permanent accordé à {user_key}.", "success")
        return redirect(url_for("staff_panel"))

    if action == "reset-password":
        temporary_password = secrets.token_urlsafe(12)
        users[user_key]["password_hash"] = generate_password_hash(temporary_password)
        users[user_key]["password_reset_at"] = utc_now()
        save_json(USERS_FILE, users)
        revoke_user_tokens(user_key)
        return render_staff_dashboard(
            temporary_password=temporary_password,
            temporary_username=user_key,
        )

    if action == "ban":
        try:
            hours = int(request.form.get("ban_hours", "0"))
        except ValueError:
            hours = 0

        if hours not in {1, 24, 72, 168, 720}:
            flash("DurÃ©e de bannissement invalide.", "error")
            return redirect(url_for("staff_panel"))

        users[user_key]["banned_until"] = (
            datetime.now(timezone.utc) + timedelta(hours=hours)
        ).isoformat()
        save_json(USERS_FILE, users)
        revoke_user_tokens(user_key)
        flash(f"{user_key} est banni pendant {hours} h.", "success")
        return redirect(url_for("staff_panel"))

    if action == "unban":
        users[user_key].pop("banned_until", None)
        save_json(USERS_FILE, users)
        flash(f"Bannissement retirÃ© pour {user_key}.", "success")
        return redirect(url_for("staff_panel"))

    if action == "delete-conversations":
        confirmation = request.form.get("confirm_delete_conversations", "").strip()
        if confirmation != "SUPPRIMER":
            flash("Écris SUPPRIMER pour confirmer l'effacement des discussions.", "error")
            return redirect(url_for("staff_panel"))

        try:
            count = remove_all_user_conversations(user_key)
        except RuntimeError as error:
            flash(str(error), "error")
            return redirect(url_for("staff_panel"))

        flash(
            f"{count} discussion(s) et leurs salons Discord ont été supprimés pour {user_key}.",
            "success",
        )
        return redirect(url_for("staff_panel"))

    if action == "delete":
        confirmation = request.form.get("confirm_username", "").strip()
        if confirmation.casefold() != user_key.casefold():
            flash("Pour supprimer ce compte, Ã©cris exactement son pseudo.", "error")
            return redirect(url_for("staff_panel"))

        try:
            remove_user_account(user_key)
        except RuntimeError as error:
            flash(str(error), "error")
            return redirect(url_for("staff_panel"))
        flash(f"Le compte {user_key}, ses conversations et ses salons Discord ont Ã©tÃ© supprimÃ©s.", "success")
        return redirect(url_for("staff_panel"))

    return "Action staff inconnue.", 404


@app.route("/staff/discord/category/delete", methods=["POST"])
def staff_delete_discord_category_channels():
    """Supprime tous les salons de la catégorie Discord NathGPT après confirmation."""
    if not staff_is_authenticated():
        return "Accès staff requis.", 403

    csrf_token = request.form.get("csrf_token", "")
    if not secrets.compare_digest(csrf_token, session.get("staff_csrf_token", "")):
        return "Requête staff invalide.", 400

    confirmation = request.form.get("confirm_category_delete", "").strip()
    if confirmation != "SUPPRIMER TOUS LES SALONS":
        flash("Écris SUPPRIMER TOUS LES SALONS pour confirmer.", "error")
        return redirect(url_for("staff_panel"))

    try:
        deleted_count = discord_bridge.delete_configured_category_channels()
    except RuntimeError as error:
        flash(str(error), "error")
        return redirect(url_for("staff_panel"))

    flash(
        f"{deleted_count} salon(s) ont été supprimés de la catégorie Discord configurée.",
        "success",
    )
    return redirect(url_for("staff_panel"))


# ============================================================
# RELAIS DISCORD
# ============================================================

@app.route(
    "/api/discord/turn",
    methods=["POST"]
)
def discord_turn():

    username = session.get("username")

    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    if get_service_status()["outage"]:
        return service_outage_response()

    payload = request.get_json(silent=True) or request.form
    question = str(payload.get("question", "")).strip()
    conversation_id = str(payload.get("conversation_id", "")).strip()

    if not question:
        return jsonify({"error": "La question est vide."}), 400

    if len(question) > 2000:
        return jsonify({"error": "La question est limitée à 2 000 caractères."}), 400

    if not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", conversation_id):
        return jsonify({"error": "Identifiant de conversation invalide."}), 400

    # Cette commande ne doit jamais partir au bot : elle sert uniquement à
    # attribuer l'accès Cricut au compte actuellement connecté.
    if question == "CRICUT_ALLOW_PERMS_TRUE":
        users = load_json(USERS_FILE, {})
        user_key = find_user_key(users, username)
        if not user_key:
            return jsonify({"error": "Compte introuvable."}), 404

        users[user_key]["cricut_enabled"] = True
        users[user_key]["cricut_enabled_at"] = utc_now()
        save_json(USERS_FILE, users)

        # La commande d'activation reste confidentielle et sa discussion est
        # effacée, côté site comme côté Discord si un salon existe déjà.
        delete_conversation(user_key, conversation_id)
        discord_bridge.delete_conversation(user_key, conversation_id)
        return jsonify({
            "cricut_activated": True,
            "message": "Compte Cricut activé.",
        })

    # La commande Pro est traitée localement afin de ne jamais être envoyée
    # au bot Discord ni conservée dans la discussion.
    if question == "PRO_ACCOUNT=True":
        users = load_json(USERS_FILE, {})
        user_key = find_user_key(users, username)
        if not user_key:
            return jsonify({"error": "Compte introuvable."}), 404

        users[user_key]["pro_enabled"] = True
        users[user_key]["pro_enabled_at"] = utc_now()
        save_json(USERS_FILE, users)
        delete_conversation(user_key, conversation_id)
        discord_bridge.delete_conversation(user_key, conversation_id)
        return jsonify({
            "pro_activated": True,
            "message": "Compte Pro activé. Les générations d'images sont déjà illimitées pour tous les comptes.",
        })

    try:
        reference_images = get_reference_images()
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    expects_image = is_image_generation_request(
        question,
        bool(reference_images),
    )

    if expects_image and not is_feature_enabled("image_generation"):
        return feature_maintenance_response("image_generation")

    if not expects_image and not is_feature_enabled("text_generation"):
        return feature_maintenance_response("text_generation")

    save_conversation_message(
        username,
        conversation_id,
        "user",
        question
    )

    try:
        job_id = discord_bridge.start_turn(
            username,
            conversation_id,
            question,
            reference_images,
            expects_image=expects_image,
        )
    except RuntimeError as error:
        # Une connexion incomplète ou une boucle Discord arrêtée doit être
        # reconstruite sans attendre une action manuelle dans Render.
        discord_bridge.request_reconnect("échec de démarrage d'une demande")
        set_service_outage("API-DISCORD")
        save_conversation_message(
            username,
            conversation_id,
            "assistant",
            str(error)
        )
        return service_outage_response()
    except Exception as error:
        app.logger.exception("Impossible d'envoyer la question à Discord")
        outage_code = outage_code_for_error(error)
        if outage_code == "API-DISCORD":
            discord_bridge.request_reconnect("échec d'envoi d'une demande")
        set_service_outage(outage_code)
        save_conversation_message(
            username,
            conversation_id,
            "assistant",
            "Nous n'avons pas pu envoyer le message à notre API. NathGPT est en cours de mise à jour."
        )
        return service_outage_response()

    return jsonify({"job_id": job_id})


@app.route("/api/cricut/start", methods=["POST"])
def start_cricut_job():
    """Démarre une décomposition d'image réservée aux comptes Cricut."""
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    if get_service_status()["outage"]:
        return service_outage_response()

    if not is_feature_enabled("cricut"):
        return feature_maintenance_response("cricut")

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key or not users[user_key].get("cricut_enabled"):
        return jsonify({"error": "Le mode Cricut n'est pas activé sur ce compte."}), 403

    try:
        reference_images = get_reference_images()
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if len(reference_images) != 1:
        return jsonify({"error": "Ajoute exactement une image à adapter en stickers."}), 400

    try:
        job_id = discord_bridge.start_cricut_job(user_key, reference_images[0])
    except RuntimeError as error:
        discord_bridge.request_reconnect("échec de démarrage Cricut")
        set_service_outage("API-DISCORD")
        return service_outage_response()
    except Exception as error:
        app.logger.exception("Impossible de démarrer la décomposition Cricut")
        outage_code = outage_code_for_error(error)
        if outage_code == "API-DISCORD":
            discord_bridge.request_reconnect("échec d'envoi Cricut")
        set_service_outage(outage_code)
        return service_outage_response()

    conversation_id = discord_bridge.job_conversation(job_id, user_key)
    save_conversation_message(
        user_key,
        conversation_id,
        "user",
        f"✦ Adaptation Cricut : {reference_images[0]['filename']}",
    )

    return jsonify({
        "job_id": job_id,
        "conversation_id": conversation_id,
    })


@app.route("/api/discord/jobs/<job_id>/events")
def discord_job_events(job_id):

    username = session.get("username")

    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    conversation_id = discord_bridge.job_conversation(
        job_id,
        username
    )

    if not conversation_id:
        return jsonify({"error": "Cette génération n'existe plus."}), 404

    def event_stream():

        while True:
            event = discord_bridge.next_event(job_id, username)

            if event is None:
                # Un vrai événement permet au navigateur de savoir que le
                # flux est toujours vivant (les commentaires SSE ne sont pas
                # visibles par EventSource côté JavaScript).
                yield "data: " + json.dumps({"type": "keep-alive"}) + "\n\n"
                continue

            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

            if event.get("type") in {"image", "text", "error", "cricut_complete"}:
                return

    response = Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream"
    )

    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"

    return response


@app.route("/api/changelog/seen", methods=["POST"])
def changelog_seen():
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401
    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key:
        return jsonify({"error": "Compte introuvable."}), 404
    users[user_key]["changelog_seen_version"] = APP_RELEASE["version"]
    users[user_key]["changelog_seen_at"] = utc_now()
    save_json(USERS_FILE, users)
    return jsonify({"ok": True, "version": APP_RELEASE["version"]})


@app.route("/api/bug-reports", methods=["GET", "POST"])
def bug_reports():
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    if request.method == "GET":
        return jsonify({"tickets": get_user_bug_reports(username)})

    payload = request.get_json(silent=True) or {}
    description = str(payload.get("description") or "").strip()
    if len(description) < 5:
        return jsonify({"error": "Décris le problème un peu plus précisément."}), 400
    report = save_bug_report(
        username,
        payload.get("category") or "Autre",
        description,
        payload.get("conversation_id") or "",
    )
    return jsonify({
        "ok": True,
        "report_id": report["id"],
        "status": report["status"],
        "status_label": report["status_label"],
    })


@app.route("/api/generation-history")
def generation_history():
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401
    return jsonify({"items": flatten_generation_history(username)})


@app.route("/api/conversations/<conversation_id>/pin", methods=["POST"])
def pin_conversation(conversation_id):
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    conversations = load_json(CONVERSATIONS_FILE, {})
    owner = next((key for key in conversations if key.casefold() == username.casefold()), None)
    if not owner:
        return jsonify({"error": "Discussion introuvable."}), 404

    conversation = next(
        (item for item in conversations.get(owner, []) if item.get("id") == conversation_id),
        None,
    )
    if not conversation:
        return jsonify({"error": "Discussion introuvable."}), 404

    payload = request.get_json(silent=True) or {}
    if "pinned" in payload:
        pinned = bool(payload.get("pinned"))
    else:
        pinned = not bool(conversation.get("pinned"))
    conversation["pinned"] = pinned
    if pinned:
        conversation["pinned_at"] = utc_now()
    else:
        conversation.pop("pinned_at", None)
    save_json(CONVERSATIONS_FILE, conversations)
    return jsonify({"ok": True, "pinned": pinned})


@app.route("/api/conversations/<conversation_id>/share", methods=["POST"])
def share_conversation(conversation_id):
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401
    conversation = get_conversation(username, conversation_id)
    if not conversation:
        return jsonify({"error": "Discussion introuvable."}), 404
    payload = request.get_json(silent=True) or {}
    try:
        hours = int(payload.get("hours", 24))
    except (TypeError, ValueError):
        hours = 24
    if hours not in {1, 24, 168}:
        hours = 24
    record = create_conversation_share(username, conversation, hours=hours)
    return jsonify({
        "ok": True,
        "url": url_for("public_shared_conversation", token=record["token"], _external=True),
        "expires_at": record["expires_at"],
    })


@app.route("/share/<token>")
def public_shared_conversation(token):
    record = get_conversation_share(token)
    if not record:
        return render_template("share.html", expired=True, conversation=None, share=None), 404
    return render_template(
        "share.html",
        expired=False,
        conversation=record.get("snapshot") or {},
        share=record,
    )


@app.route("/api/conversations")
def conversations():

    username = session.get("username")

    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    return jsonify({"conversations": get_conversation_summaries(username)})


@app.route("/api/conversations/<conversation_id>")
def conversation_detail(conversation_id):

    username = session.get("username")

    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    conversation = get_conversation(username, conversation_id)

    if not conversation:
        return jsonify({"error": "Discussion introuvable."}), 404

    return jsonify({"conversation": conversation})


@app.route("/api/automatic-generations")
def automatic_generations():
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key or not users[user_key].get("cricut_enabled"):
        return jsonify({"error": "Le mode Cricut n'est pas activé sur ce compte."}), 403

    return jsonify({"generations": get_automatic_generations(user_key)})


@app.route("/api/automatic-generations/<generation_id>/opened", methods=["POST"])
def automatic_generation_opened(generation_id):
    username = session.get("username")
    if not username:
        return jsonify({"error": "Connexion requise."}), 401
    if not re.fullmatch(r"auto-\d{4}-\d{2}-\d{2}", generation_id):
        return jsonify({"error": "Identifiant de génération invalide."}), 400

    users = load_json(USERS_FILE, {})
    user_key = find_user_key(users, username)
    if not user_key or not users[user_key].get("cricut_enabled"):
        return jsonify({"error": "Le mode Cricut n'est pas activé sur ce compte."}), 403
    if not mark_automatic_generation_opened(user_key, generation_id):
        return jsonify({"error": "Génération introuvable."}), 404
    return jsonify({"ok": True})


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    username = session.get(
        "username"
    )


    current_ip = client_ip()


    raw_token = request.cookies.get(
        REMEMBER_COOKIE_NAME
    )


    # Supprime le token du JSON

    revoke_token(
        raw_token
    )


    # En cas de déconnexion manuelle,
    # retire l'IP actuelle des IP reconnues.

    if username:

        users = load_json(
            USERS_FILE,
            {}
        )


        user_key = find_user_key(
            users,
            username
        )


        if user_key:

            known_ips = users[
                user_key
            ].get(
                "known_ips",
                []
            )


            users[user_key][
                "known_ips"
            ] = [

                ip

                for ip in known_ips

                if ip != current_ip

            ]


            save_json(
                USERS_FILE,
                users
            )


    # Supprime session

    session.clear()


    response = make_response(

        redirect(
            url_for("login")
        )

    )


    # Supprime cookie

    response.delete_cookie(
        REMEMBER_COOKIE_NAME
    )


    return response


# ============================================================
# ERREUR 404
# ============================================================

@app.errorhandler(404)
def page_not_found(error):

    if request.path.startswith("/static/"):
        return "", 404

    if session.get("username"):

        return redirect(
            url_for("chat")
        )


    return redirect(
        url_for("login")
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 55)
    print("           NathGPT Server")
    print("=" * 55)
    print()
    print("Serveur lancé :")
    print()
    print("http://127.0.0.1:5000")
    print()
    print("CTRL + C pour arrêter.")
    print()
    print("=" * 55)
    print()


    app.run(

        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                "5000"
            )
        ),

        # Le reloader démarre le programme deux fois et provoque le
        # SystemExit affiché par VS Code. Il doit rester désactivé car
        # le client Discord est lui aussi démarré dans ce processus.
        debug=False,

        use_reloader=False

    )
