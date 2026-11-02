"""Comptes, sessions, conversations et compteur côté serveur (SQLite et Supabase simulé)."""

import asyncio
import hashlib
import json

import httpx

from server import Settings, create_app
from services.store import SupabaseStore, hash_password, session_digest, verify_password

PASSWORD = 'motdepasse-solide'


def run(coroutine):
    return asyncio.run(coroutine)


def upstream():
    def handler(_request):
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=b'event: delta\ndata: {"text":"Pong"}\n\nevent: done\ndata: {}\n\n')
    return httpx.MockTransport(handler)


def site(tmp_path):
    app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=upstream())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver'), app


def test_signup_login_me_logout(tmp_path):
    async def scenario():
        client, _ = site(tmp_path)
        async with client:
            assert (await client.get('/api/auth/me')).status_code == 401
            created = await client.post('/api/auth/signup', json={'pseudo': 'Alice', 'password': PASSWORD})
            assert created.status_code == 200
            assert created.json()['account'] == {'key': 'alice', 'pseudo': 'Alice', 'tokens_used': 0, 'usage_estimated': False}
            assert 'httponly' in created.headers['set-cookie'].lower()
            assert (await client.get('/api/auth/me')).json()['account']['pseudo'] == 'Alice'
            duplicate = await client.post('/api/auth/signup', json={'pseudo': 'ALICE', 'password': PASSWORD})
            assert duplicate.status_code == 409
            await client.post('/api/session/logout')
            assert (await client.get('/api/auth/me')).status_code == 401
            wrong = await client.post('/api/auth/login', json={'pseudo': 'alice', 'password': 'mauvais-mot'})
            assert wrong.status_code == 401
            assert (await client.post('/api/auth/login', json={'pseudo': 'alice', 'password': PASSWORD})).status_code == 200
            assert (await client.get('/api/auth/me')).status_code == 200

    run(scenario())


def test_session_id_is_stored_hashed(tmp_path):
    async def scenario():
        client, app = site(tmp_path)
        async with client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            sid = client.cookies.get('nathgpt_backend_sid')
        import sqlite3
        rows = sqlite3.connect(tmp_path / 'db.sqlite3').execute('SELECT id_hash FROM nathgpt_sessions').fetchall()
        assert rows == [(session_digest(sid),)]

    run(scenario())


def test_login_rate_limited(tmp_path):
    async def scenario():
        client, _ = site(tmp_path)
        async with client:
            codes = [(await client.post('/api/auth/login', json={'pseudo': 'nobody', 'password': 'mauvais-mot'})).status_code for _ in range(11)]
            assert codes[:10] == [401] * 10 and codes[10] == 429

    run(scenario())


def test_old_site_werkzeug_hash_still_works():
    # Même calcul que werkzeug.security.generate_password_hash (méthode scrypt par défaut).
    salt = 'AbCdEfGh12345678'
    digest = hashlib.scrypt(b'ancien-mot', salt=salt.encode(), n=32768, r=8, p=1, maxmem=132 * 32768 * 8).hex()
    stored = f'scrypt:32768:8:1${salt}${digest}'
    assert verify_password(stored, 'ancien-mot')
    assert not verify_password(stored, 'autre-mot')
    pbkdf2 = 'pbkdf2:sha256:1000$sel$' + hashlib.pbkdf2_hmac('sha256', b'pw-pbkdf2', b'sel', 1000).hex()
    assert verify_password(pbkdf2, 'pw-pbkdf2')
    assert verify_password(hash_password('nouveau-mot'), 'nouveau-mot')
    assert not verify_password('inconnu', 'x')


def test_conversations_sync_and_ownership(tmp_path):
    async def scenario():
        alice, app = site(tmp_path)
        bob = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        async with alice, bob:
            await alice.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            await bob.post('/api/auth/signup', json={'pseudo': 'bob', 'password': PASSWORD})
            messages = [{'id': 'm1', 'role': 'user', 'content': 'Salut'}, {'id': 'm2', 'role': 'assistant', 'content': 'Pong', 'state': 'done'}]
            saved = await alice.put('/api/conversations/conversation_1', json={'title': 'Salut', 'messages': messages, 'created_at': 1, 'updated_at': 2})
            assert saved.status_code == 200
            listed = (await alice.get('/api/conversations')).json()['conversations']
            assert listed == [{'id': 'conversation_1', 'title': 'Salut', 'messages': messages, 'created_at': 1, 'updated_at': 2}]
            stolen = await bob.put('/api/conversations/conversation_1', json={'title': 'X', 'messages': [], 'updated_at': 3})
            assert stolen.status_code == 403
            assert (await bob.get('/api/conversations')).json()['conversations'] == []
            await bob.delete('/api/conversations/conversation_1')
            assert len((await alice.get('/api/conversations')).json()['conversations']) == 1
            await alice.delete('/api/conversations/conversation_1')
            assert (await alice.get('/api/conversations')).json()['conversations'] == []

    run(scenario())


def test_usage_counted_on_server(tmp_path):
    async def scenario():
        client, _ = site(tmp_path)
        async with client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            response = await client.post('/api/chat', json={'prompt': 'ping', 'conversation_id': 'conversation_1', 'stream': True})
            done = json.loads(response.text.split('event: done\ndata: ', 1)[1].split('\n', 1)[0])
            assert done['account_tokens_used'] == 2 and done['usage_estimated'] is True
            assert (await client.get('/api/auth/me')).json()['account']['tokens_used'] == 2

    run(scenario())


def test_foreign_origin_rejected(tmp_path):
    async def scenario():
        client, _ = site(tmp_path)
        async with client:
            denied = await client.post('/api/auth/signup', headers={'Origin': 'https://evil.example'}, json={'pseudo': 'alice', 'password': PASSWORD})
            assert denied.status_code == 403
            allowed = await client.post('/api/auth/signup', headers={'Origin': 'https://testserver'}, json={'pseudo': 'alice', 'password': PASSWORD})
            assert allowed.status_code == 200

    run(scenario())


def test_health_aliases(tmp_path):
    async def scenario():
        client, _ = site(tmp_path)
        async with client:
            assert (await client.get('/health')).json()['storage'] == 'sqlite'
            assert (await client.get('/api/health')).status_code == 200

    run(scenario())


def test_supabase_store_requests():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/rpc/nathgpt_claim_conversation'):
            return httpx.Response(200, json=True)
        if request.method == 'POST' and request.url.path.endswith('/nathgpt_accounts'):
            return httpx.Response(409, json={'code': '23505'})
        if request.url.path.endswith('/nathgpt_sessions') and request.method == 'GET':
            return httpx.Response(200, json=[{'expires_at': '2999-01-01T00:00:00+00:00', 'account': {'key': 'alice', 'pseudo': 'Alice', 'tokens_used': 5, 'usage_estimated': True}}])
        return httpx.Response(201)

    async def scenario():
        store = SupabaseStore('https://exemple.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handler))
        assert await store.create_account('alice', 'Alice', 'h') is False  # 409 = pseudo pris
        assert await store.claim_conversation('alice', 'conversation_1') is True
        account = await store.session_account('cookie')
        assert account == {'key': 'alice', 'pseudo': 'Alice', 'tokens_used': 5, 'usage_estimated': True}
        session_call = calls[-1]
        assert session_call.url.params['id_hash'] == f"eq.{session_digest('cookie')}"
        assert session_call.headers['apikey'] == 'sb_secret_test'
        assert 'authorization' not in session_call.headers  # clé sb_secret_ : pas de Bearer
        assert str(session_call.url).startswith('https://exemple.supabase.co/rest/v1/')

    run(scenario())
