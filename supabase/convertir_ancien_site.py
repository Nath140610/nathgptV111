#!/usr/bin/env python3
"""Convertit les données de l'ancien site NathGPT (dossier data/) en SQL pour Supabase.

  python supabase/convertir_ancien_site.py CHEMIN/VERS/data supabase/import_ancien_site.local.sql

Repris : comptes (pseudo + hachage du mot de passe, les anciens mots de passe restent
valables) et conversations. Non repris : adresses IP, jetons API, données Discord,
images de l'ancien serveur. Le fichier produit contient des données personnelles :
ne le committez pas (*.local.sql est ignoré par git). À exécuter APRÈS schema.sql.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

CONVERSATION_RE = re.compile(r'^[A-Za-z0-9_-]{8,128}$')


def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def to_ms(value, fallback: int) -> int:
    if isinstance(value, (int, float)) and value > 0:
        return int(value if value > 10**11 else value * 1000)
    if isinstance(value, str) and value:
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return int(date.timestamp() * 1000)
        except ValueError:
            pass
    return fallback


def convert_message(message: dict, fallback: int) -> dict | None:
    role = message.get('role')
    if role not in ('user', 'assistant'):
        return None
    content = str(message.get('content') or '')
    if message.get('image_url') or message.get('cricut_images'):
        content = (content + '\n\n' if content else '') + '*(Image de l’ancienne version de NathGPT, non reprise.)*'
    created = to_ms(message.get('created_at'), fallback)
    converted = {'id': uuid.uuid4().hex, 'role': role, 'content': content, 'createdAt': created, 'task': 'chat'}
    if role == 'assistant':
        converted['state'] = 'done'
    return converted


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    data_dir, output = Path(sys.argv[1]), Path(sys.argv[2])
    users = json.loads((data_dir / 'users.json').read_text(encoding='utf-8'))
    conversations_path = data_dir / 'conversations.json'
    conversations = json.loads(conversations_path.read_text(encoding='utf-8')) if conversations_path.exists() else {}
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    lines = ['-- Import des données de l’ancien site NathGPT. Exécuter après schema.sql.', 'begin;']
    keys: dict[str, str] = {}
    skipped_users = []
    for name, user in users.items():
        pseudo = str(name).strip()
        key = pseudo.casefold()
        if not 3 <= len(pseudo) <= 24 or key in keys.values() or not str(user.get('password_hash', '')).startswith(('scrypt:', 'pbkdf2:')):
            skipped_users.append(pseudo)
            continue
        keys[name] = key
        created = datetime.fromtimestamp(to_ms(user.get('created_at'), now) / 1000, timezone.utc).isoformat()
        lines.append(
            'insert into public.nathgpt_accounts (key, pseudo, password_hash, created_at) values '
            f"({sql_text(key)}, {sql_text(pseudo)}, {sql_text(user['password_hash'])}, {sql_text(created)}) on conflict (key) do nothing;"
        )

    imported = skipped_conversations = 0
    for owner, items in conversations.items():
        key = keys.get(owner) or next((k for n, k in keys.items() if n.casefold() == str(owner).casefold()), None)
        if not key:
            skipped_conversations += len(items)
            continue
        for item in items:
            created = to_ms(item.get('created_at'), now)
            updated = to_ms(item.get('updated_at'), created)
            messages = [m for m in (convert_message(m, created) for m in item.get('messages', [])) if m]
            if not messages:
                continue
            conversation_id = str(item.get('id') or '')
            if not CONVERSATION_RE.fullmatch(conversation_id):
                conversation_id = uuid.uuid4().hex
            title = str(item.get('title') or messages[0]['content'].split('\n')[0])[:120] or 'Conversation'
            payload = json.dumps(messages, ensure_ascii=False)
            lines.append(
                'insert into public.nathgpt_conversations (id, account_key, title, messages, created_at, updated_at) values '
                f'({sql_text(conversation_id)}, {sql_text(key)}, {sql_text(title)}, {sql_text(payload)}::jsonb, {created}, {updated}) on conflict (id) do nothing;'
            )
            imported += 1

    lines.append('commit;')
    output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'{len(keys)} comptes et {imported} conversations écrits dans {output}')
    if skipped_users:
        print(f'{len(skipped_users)} compte(s) ignoré(s) (pseudo invalide, doublon ou hachage inconnu).')
    if skipped_conversations:
        print(f'{skipped_conversations} conversation(s) ignorée(s) : propriétaire absent de users.json.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
