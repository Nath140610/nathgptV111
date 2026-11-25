"""API développeur /v1 : tokens ngt_, chat, images (SQLite et Supabase simulé)."""

import asyncio
import base64
import json
import sqlite3

import httpx

from server import Settings, create_app
from services.store import MAX_API_KEYS, SupabaseStore, session_digest

PASSWORD = 'motdepasse-solide'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def run(coroutine):
    return asyncio.run(coroutine)


def site(tmp_path, sent=None):
    def handler(request):
        body = json.loads(request.content)
        if sent is not None:
            sent.append(body)
        if body.get('response_type') == 'image':
            event = json.dumps({'base64': base64.b64encode(PNG).decode(), 'mime_type': 'image/png'})
            content = f'event: image\ndata: {event}\n\nevent: done\ndata: {{}}\n\n'.encode()
        else:
            content = b'event: delta\ndata: {"text":"Pong"}\n\nevent: done\ndata: {"total_tokens": 42}\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=content)

    app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=httpx.MockTransport(handler))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')


async def signup_and_token(client, name='Mon bot'):
    await client.post('/api/auth/signup', json={'pseudo': 'Alice', 'password': PASSWORD})
    client.cookies.clear()  # l'API ne doit jamais dépendre du cookie du site
    return await client.post('/v1/auth/token', json={'username': 'alice', 'password': PASSWORD, 'name': name})


def test_token_lifecycle(tmp_path):
    async def scenario():
        async with site(tmp_path) as client:
            created = await signup_and_token(client)
            assert created.status_code == 201
            token = created.json()['token']
            assert token.startswith('ngt_')
            headers = {'Authorization': f'Bearer {token}'}

            keys = (await client.get('/v1/auth/keys', headers=headers)).json()
            assert [k['name'] for k in keys['data']] == ['Mon bot']
            assert keys['current_key_id'] == created.json()['id']

            chat = await client.post('/v1/chat/completions', headers=headers, json={'model': 'nathgpt', 'messages': [{'role': 'user', 'content': 'Ping'}]})
            assert chat.status_code == 200
            assert chat.json()['choices'][0]['message']['content'] == 'Pong'
            assert chat.json()['usage']['total_tokens'] == 42
            assert (await client.get('/v1/usage', headers=headers)).json()['tokens_used'] == 42

            assert (await client.delete('/v1/auth/token', headers=headers)).json()['revoked'] is True
            refused = await client.get('/v1/usage', headers=headers)
            assert refused.status_code == 401
            assert refused.json()['error']['code'] == 'invalid_api_key'

        rows = sqlite3.connect(tmp_path / 'db.sqlite3').execute('SELECT key_hash FROM nathgpt_api_keys').fetchall()
        assert rows == [(session_digest(token),)]  # la clé elle-même n'est jamais stockée

    run(scenario())


def test_bad_credentials_and_missing_key(tmp_path):
    async def scenario():
        async with site(tmp_path) as client:
            await client.post('/api/auth/signup', json={'pseudo': 'Alice', 'password': PASSWORD})
            wrong = await client.post('/v1/auth/token', json={'username': 'alice', 'password': 'mauvais-mot'})
            assert wrong.status_code == 401
            assert wrong.json()['error']['code'] == 'invalid_api_key'
            unknown = await client.post('/v1/auth/token', json={'pseudo': 'personne', 'password': PASSWORD})
            assert unknown.status_code == 401
            missing = await client.get('/v1/usage')
            assert missing.status_code == 401 and 'Bearer' in missing.json()['error']['message']
            # La session cookie du site n'ouvre pas l'API.
            assert (await client.get('/v1/auth/keys')).status_code == 401

    run(scenario())


def test_key_limit(tmp_path):
    async def scenario():
        async with site(tmp_path) as client:
            assert (await signup_and_token(client)).status_code == 201
            for _ in range(MAX_API_KEYS - 1):
                assert (await client.post('/v1/auth/token', json={'username': 'alice', 'password': PASSWORD})).status_code == 201
            too_many = await client.post('/v1/auth/token', json={'username': 'alice', 'password': PASSWORD})
            assert too_many.status_code == 409

    run(scenario())


def test_messages_become_one_prompt(tmp_path):
    async def scenario():
        sent = []
        async with site(tmp_path, sent) as client:
            headers = {'Authorization': f'Bearer {(await signup_and_token(client)).json()["token"]}'}
            messages = [
                {'role': 'system', 'content': 'Réponds en anglais.'},
                {'role': 'user', 'content': 'Bonjour'},
                {'role': 'assistant', 'content': 'Hello'},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'Ça va ?'}]},
            ]
            chat = await client.post('/v1/chat/completions', headers=headers, json={'messages': messages, 'conversation_id': 'mon-script-1'})
            assert chat.status_code == 200 and chat.json()['conversation_id'] == 'mon-script-1'
            assert sent[-1]['prompt'] == 'Instructions : Réponds en anglais.\n\nUtilisateur : Bonjour\n\nNathGPT : Hello\n\nUtilisateur : Ça va ?'
            assert sent[-1]['conversation_id'] == 'mon-script-1'

            assistant_last = await client.post('/v1/chat/completions', headers=headers, json={'messages': [{'role': 'assistant', 'content': 'x'}]})
            assert assistant_last.status_code == 400
            streamed = await client.post('/v1/chat/completions', headers=headers, json={'stream': True, 'messages': [{'role': 'user', 'content': 'x'}]})
            assert streamed.status_code == 400

    run(scenario())


def test_conversation_of_another_account_is_refused(tmp_path):
    async def scenario():
        async with site(tmp_path) as client:
            await client.post('/api/auth/signup', json={'pseudo': 'Bob', 'password': PASSWORD})
            await client.post('/api/chat', json={'prompt': 'x', 'conversation_id': 'conversation-bob', 'stream': True})
            headers = {'Authorization': f'Bearer {(await signup_and_token(client)).json()["token"]}'}
            stolen = await client.post('/v1/chat/completions', headers=headers, json={'conversation_id': 'conversation-bob', 'messages': [{'role': 'user', 'content': 'x'}]})
            assert stolen.status_code == 403

    run(scenario())


def test_image_generation(tmp_path):
    async def scenario():
        async with site(tmp_path) as client:
            headers = {'Authorization': f'Bearer {(await signup_and_token(client)).json()["token"]}'}
            image = await client.post('/v1/images/generations', headers=headers, json={'prompt': 'Un chat vert'})
            assert image.status_code == 200
            assert base64.b64decode(image.json()['data'][0]['b64_json']) == PNG
            assert (await client.get('/v1/usage', headers=headers)).json()['saved_eur'] == 0.05

    run(scenario())


def test_supabase_api_key_requests():
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == 'GET' and request.url.path.endswith('/nathgpt_api_keys'):
            if 'key_hash' in request.url.params:
                return httpx.Response(200, json=[{'id': 'key_0123456789abcdef', 'account': {'key': 'alice', 'pseudo': 'Alice', 'tokens_used': 3, 'usage_estimated': False}}])
            return httpx.Response(200, json=[{'id': f'key_{i}'} for i in range(MAX_API_KEYS)])
        return httpx.Response(204)

    async def scenario():
        store = SupabaseStore('https://exemple.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handler))
        assert await store.create_api_key('alice', 'Bot') is None  # déjà MAX_API_KEYS clés actives
        account = await store.api_key_account('ngt_secret')
        assert account == {'key': 'alice', 'pseudo': 'Alice', 'tokens_used': 3, 'usage_estimated': False, 'api_key_id': 'key_0123456789abcdef'}
        lookup = next(c for c in calls if 'key_hash' in c.url.params)
        assert lookup.url.params['key_hash'] == f"eq.{session_digest('ngt_secret')}"
        assert lookup.url.params['revoked_at'] == 'is.null'

    run(scenario())
