"""Stockage serveur : comptes, sessions, compteur d'usage et conversations.

SQLite en local, Supabase (API REST PostgREST) en production. La clé secrète
Supabase reste sur le serveur ; les tables sont fermées par RLS (voir
supabase/schema.sql). Les identifiants de session ne sont stockés que hachés.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import sqlite3
import string
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

SESSION_SECONDS = 60 * 60 * 24 * 30
SALT_ALPHABET = string.ascii_letters + string.digits


def hash_password(password: str) -> str:
    """Format Werkzeug « scrypt:n:r:p$sel$hash » : compatible avec l'ancien site."""
    n, r, p = 32768, 8, 1
    salt = ''.join(secrets.choice(SALT_ALPHABET) for _ in range(16))
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=n, r=r, p=p, maxmem=132 * n * r * p).hex()
    return f'scrypt:{n}:{r}:{p}${salt}${digest}'


def verify_password(stored: str, password: str) -> bool:
    """Vérifie les hachages scrypt et pbkdf2 au format Werkzeug."""
    try:
        method, salt, expected = stored.split('$', 2)
        parts = method.split(':')
        if parts[0] == 'scrypt':
            n, r, p = (int(value) for value in parts[1:4])
            actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=n, r=r, p=p, maxmem=132 * n * r * p).hex()
        elif parts[0] == 'pbkdf2':
            algorithm = parts[1] if len(parts) > 1 else 'sha256'
            iterations = int(parts[2]) if len(parts) > 2 else 600000
            actual = hashlib.pbkdf2_hmac(algorithm, password.encode(), salt.encode(), iterations).hex()
        else:
            return False
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def session_digest(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def public_account(row: dict) -> dict:
    return {
        'key': row['key'], 'pseudo': row['pseudo'],
        'tokens_used': int(row.get('tokens_used') or 0),
        'usage_estimated': bool(row.get('usage_estimated')),
    }


class StoreError(Exception):
    pass


class SQLiteStore:
    """Développement local : fichier SQLite, mêmes tables que Supabase."""

    kind = 'sqlite'

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS nathgpt_accounts (key TEXT PRIMARY KEY, pseudo TEXT NOT NULL, password_hash TEXT NOT NULL, tokens_used INTEGER NOT NULL DEFAULT 0, usage_estimated INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS nathgpt_sessions (id_hash TEXT PRIMARY KEY, account_key TEXT NOT NULL REFERENCES nathgpt_accounts(key) ON DELETE CASCADE, expires_at REAL NOT NULL)')
            db.execute("CREATE TABLE IF NOT EXISTS nathgpt_conversations (id TEXT PRIMARY KEY, account_key TEXT NOT NULL REFERENCES nathgpt_accounts(key) ON DELETE CASCADE, title TEXT NOT NULL DEFAULT '', messages TEXT NOT NULL DEFAULT '[]', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    async def _run(self, function, *args):
        return await asyncio.to_thread(function, *args)

    def _create_account(self, key, pseudo, password_hash):
        with self.lock, self._connect() as db:
            try:
                db.execute('INSERT INTO nathgpt_accounts VALUES (?, ?, ?, 0, 0, ?)', (key, pseudo, password_hash, time.time()))
                return True
            except sqlite3.IntegrityError:
                return False

    async def create_account(self, key: str, pseudo: str, password_hash: str) -> bool:
        return await self._run(self._create_account, key, pseudo, password_hash)

    def _get_account(self, key):
        with self.lock, self._connect() as db:
            row = db.execute('SELECT * FROM nathgpt_accounts WHERE key=?', (key,)).fetchone()
            return dict(row) if row else None

    async def get_account(self, key: str) -> dict | None:
        return await self._run(self._get_account, key)

    def _create_session(self, key):
        sid = secrets.token_urlsafe(32)
        with self.lock, self._connect() as db:
            db.execute('DELETE FROM nathgpt_sessions WHERE expires_at<=?', (time.time(),))
            db.execute('INSERT INTO nathgpt_sessions VALUES (?, ?, ?)', (session_digest(sid), key, time.time() + SESSION_SECONDS))
        return sid

    async def create_session(self, key: str) -> str:
        return await self._run(self._create_session, key)

    def _session_account(self, sid):
        with self.lock, self._connect() as db:
            row = db.execute('SELECT a.*, s.expires_at AS session_expires FROM nathgpt_sessions s JOIN nathgpt_accounts a ON a.key=s.account_key WHERE s.id_hash=?', (session_digest(sid),)).fetchone()
            if not row:
                return None
            if row['session_expires'] <= time.time():
                db.execute('DELETE FROM nathgpt_sessions WHERE id_hash=?', (session_digest(sid),))
                return None
            return public_account(dict(row))

    async def session_account(self, sid: str | None) -> dict | None:
        return await self._run(self._session_account, sid) if sid else None

    def _revoke(self, sid):
        with self.lock, self._connect() as db:
            db.execute('DELETE FROM nathgpt_sessions WHERE id_hash=?', (session_digest(sid),))

    async def revoke(self, sid: str | None) -> None:
        if sid:
            await self._run(self._revoke, sid)

    def _claim(self, key, conversation_id):
        now = int(time.time() * 1000)
        with self.lock, self._connect() as db:
            db.execute('INSERT OR IGNORE INTO nathgpt_conversations (id, account_key, created_at, updated_at) VALUES (?, ?, ?, ?)', (conversation_id, key, now, now))
            row = db.execute('SELECT account_key FROM nathgpt_conversations WHERE id=?', (conversation_id,)).fetchone()
            return bool(row and row[0] == key)

    async def claim_conversation(self, key: str, conversation_id: str) -> bool:
        return await self._run(self._claim, key, conversation_id)

    def _add_usage(self, key, tokens, estimated):
        with self.lock, self._connect() as db:
            db.execute('UPDATE nathgpt_accounts SET tokens_used=tokens_used+?, usage_estimated=MAX(usage_estimated, ?) WHERE key=?', (tokens, int(estimated), key))
            row = db.execute('SELECT tokens_used FROM nathgpt_accounts WHERE key=?', (key,)).fetchone()
            return int(row[0]) if row else None

    async def add_usage(self, key: str, tokens: int, estimated: bool) -> int | None:
        return await self._run(self._add_usage, key, tokens, estimated)

    def _list(self, key):
        with self.lock, self._connect() as db:
            rows = db.execute("SELECT id, title, messages, created_at, updated_at FROM nathgpt_conversations WHERE account_key=? AND messages<>'[]' ORDER BY updated_at DESC LIMIT 200", (key,)).fetchall()
            return [{**dict(row), 'messages': json.loads(row['messages'])} for row in rows]

    async def list_conversations(self, key: str) -> list[dict]:
        return await self._run(self._list, key)

    def _save(self, key, conversation_id, title, messages, created_at, updated_at):
        with self.lock, self._connect() as db:
            cursor = db.execute(
                'INSERT INTO nathgpt_conversations VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, messages=excluded.messages, updated_at=excluded.updated_at WHERE nathgpt_conversations.account_key=excluded.account_key',
                (conversation_id, key, title, json.dumps(messages, ensure_ascii=False), created_at, updated_at),
            )
            return cursor.rowcount > 0

    async def save_conversation(self, key, conversation_id, title, messages, created_at, updated_at) -> bool:
        return await self._run(self._save, key, conversation_id, title, messages, created_at, updated_at)

    def _delete(self, key, conversation_id):
        with self.lock, self._connect() as db:
            db.execute('DELETE FROM nathgpt_conversations WHERE id=? AND account_key=?', (conversation_id, key))

    async def delete_conversation(self, key: str, conversation_id: str) -> None:
        await self._run(self._delete, key, conversation_id)


class SupabaseStore:
    """Production : Supabase via son API REST, avec la clé secrète du serveur."""

    kind = 'supabase'

    def __init__(self, url: str, key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        url = url.strip().rstrip('/')
        if not url.startswith('https://'):
            raise ValueError('SUPABASE_URL doit commencer par https://')
        headers = {'apikey': key.strip(), 'Content-Type': 'application/json'}
        # Ancienne clé service_role (JWT) : aussi dans Authorization. Les clés sb_secret_ passent par apikey.
        if key.strip().startswith('eyJ'):
            headers['Authorization'] = f'Bearer {key.strip()}'
        self.client = httpx.AsyncClient(base_url=f'{url}/rest/v1', headers=headers, timeout=httpx.Timeout(10, connect=5), transport=transport)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise StoreError('Supabase injoignable') from error
        if response.status_code >= 400 and response.status_code != 409:
            raise StoreError(f'Supabase HTTP {response.status_code}')
        return response

    async def _rpc(self, name: str, payload: dict):
        return (await self._request('POST', f'/rpc/{name}', json=payload)).json()

    async def create_account(self, key, pseudo, password_hash) -> bool:
        response = await self._request('POST', '/nathgpt_accounts', json={'key': key, 'pseudo': pseudo, 'password_hash': password_hash}, headers={'Prefer': 'return=minimal'})
        return response.status_code != 409

    async def get_account(self, key) -> dict | None:
        rows = (await self._request('GET', '/nathgpt_accounts', params={'key': f'eq.{key}', 'select': 'key,pseudo,password_hash,tokens_used,usage_estimated'})).json()
        return rows[0] if rows else None

    async def create_session(self, key) -> str:
        sid = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)).isoformat()
        await self._request('POST', '/nathgpt_sessions', json={'id_hash': session_digest(sid), 'account_key': key, 'expires_at': expires}, headers={'Prefer': 'return=minimal'})
        return sid

    async def session_account(self, sid) -> dict | None:
        if not sid:
            return None
        rows = (await self._request('GET', '/nathgpt_sessions', params={
            'id_hash': f'eq.{session_digest(sid)}',
            'select': 'expires_at,account:nathgpt_accounts(key,pseudo,tokens_used,usage_estimated)',
        })).json()
        if not rows or not rows[0].get('account'):
            return None
        if datetime.fromisoformat(rows[0]['expires_at']) <= datetime.now(timezone.utc):
            await self.revoke(sid)
            return None
        return public_account(rows[0]['account'])

    async def revoke(self, sid) -> None:
        if sid:
            await self._request('DELETE', '/nathgpt_sessions', params={'id_hash': f'eq.{session_digest(sid)}'})

    async def claim_conversation(self, key, conversation_id) -> bool:
        return bool(await self._rpc('nathgpt_claim_conversation', {'p_id': conversation_id, 'p_account_key': key}))

    async def add_usage(self, key, tokens, estimated) -> int | None:
        total = await self._rpc('nathgpt_add_usage', {'p_account_key': key, 'p_tokens': tokens, 'p_estimated': estimated})
        return int(total) if total is not None else None

    async def list_conversations(self, key) -> list[dict]:
        return (await self._request('GET', '/nathgpt_conversations', params={
            'account_key': f'eq.{key}', 'messages': 'neq.[]',
            'select': 'id,title,messages,created_at,updated_at', 'order': 'updated_at.desc', 'limit': '200',
        })).json()

    async def save_conversation(self, key, conversation_id, title, messages, created_at, updated_at) -> bool:
        return bool(await self._rpc('nathgpt_save_conversation', {
            'p_id': conversation_id, 'p_account_key': key, 'p_title': title, 'p_messages': messages,
            'p_created_at': created_at, 'p_updated_at': updated_at,
        }))

    async def delete_conversation(self, key, conversation_id) -> None:
        await self._request('DELETE', '/nathgpt_conversations', params={'id': f'eq.{conversation_id}', 'account_key': f'eq.{key}'})
