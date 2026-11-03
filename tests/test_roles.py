"""Rôles donnés par un admin (maintenant ou programmés), notifications, arrêt et libération de NathGPT."""

import asyncio
import json
import sqlite3
import sys
import time
import types
from contextlib import asynccontextmanager

import httpx

from server import Settings, create_app

PASSWORD = 'motdepasse-solide'
TOKEN = 'jeton-api-' + 'x' * 40


@asynccontextmanager
async def closing(*clients):
    try:
        yield
    finally:
        for client in clients:
            await client.aclose()


def run(coroutine):
    return asyncio.run(coroutine)


def fake_push(monkeypatch, pushed):
    module = types.ModuleType('pywebpush')

    class WebPushException(Exception):
        response = None

    def webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl):
        pushed.append(json.loads(data))
    module.webpush, module.WebPushException = webpush, WebPushException
    monkeypatch.setitem(sys.modules, 'pywebpush', module)


async def setup(tmp_path, transport=None):
    db = tmp_path / 'db.sqlite3'
    settings = Settings('https://vm.example.com', TOKEN, db, vapid_public='BPublic', vapid_private='private')
    app = create_app(settings, transport=transport or httpx.MockTransport(lambda r: httpx.Response(404)))
    admin = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
    await admin.post('/api/auth/signup', json={'pseudo': 'nath', 'password': PASSWORD})
    await alice.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE nathgpt_accounts SET is_admin=1 WHERE key='nath'")
    await alice.post('/api/push/subscribe', json={'endpoint': 'https://push.example/alice', 'keys': {'p256dh': 'BKey', 'auth': 'auth'}})
    return app, admin, alice, db


def test_give_role_now_and_notify(tmp_path, monkeypatch):
    pushed = []
    fake_push(monkeypatch, pushed)

    async def scenario():
        app, admin, alice, _ = await setup(tmp_path)
        async with closing(admin, alice):
            assert (await alice.get('/api/admin/accounts')).status_code == 403
            assert (await alice.post('/api/admin/grants', json={'account_key': 'alice', 'role': 'cricut'})).status_code == 403
            accounts = (await admin.get('/api/admin/accounts')).json()['accounts']
            assert {a['key'] for a in accounts} == {'nath', 'alice'}

            given = (await admin.post('/api/admin/grants', json={'account_key': 'alice', 'role': 'cricut', 'grant_at': None})).json()
            assert given['applied'] is True
            assert (await alice.get('/api/auth/me')).json()['account']['cricut'] is True
            assert pushed[-1]['view'] == 'cricut' and 'l’accès Cricut' in pushed[-1]['body']

            notices = (await alice.get('/api/notices')).json()['notices']
            assert [n['role'] for n in notices] == ['cricut']
            await alice.post(f"/api/notices/{notices[0]['id']}/seen")
            assert (await alice.get('/api/notices')).json()['notices'] == []

            assert (await admin.post('/api/admin/grants', json={'account_key': 'personne', 'role': 'cricut'})).status_code == 404
            assert (await admin.post('/api/admin/grants', json={'account_key': 'alice', 'role': 'dieu'})).status_code == 400
            assert (await admin.post('/api/admin/roles/revoke', json={'account_key': 'alice', 'role': 'cricut'})).status_code == 200
            assert (await alice.get('/api/auth/me')).json()['account']['cricut'] is False
            assert (await admin.post('/api/admin/roles/revoke', json={'account_key': 'nath', 'role': 'is_admin'})).status_code == 400

    run(scenario())


def test_scheduled_role(tmp_path, monkeypatch):
    pushed = []
    fake_push(monkeypatch, pushed)

    async def scenario():
        app, admin, alice, db = await setup(tmp_path)
        async with closing(admin, alice):
            later = int((time.time() + 3600) * 1000)
            planned = (await admin.post('/api/admin/grants', json={'account_key': 'alice', 'role': 'is_admin', 'grant_at': later})).json()
            assert planned['applied'] is False
            grants = (await admin.get('/api/admin/grants')).json()['grants']
            assert grants[0]['pseudo'] == 'alice' and grants[0]['grant_at'] == later
            assert (await alice.get('/api/auth/me')).json()['account']['is_admin'] is False
            past = (await admin.post('/api/admin/grants', json={'account_key': 'alice', 'role': 'cricut', 'grant_at': int((time.time() - 3600) * 1000)}))
            assert past.status_code == 400

            # L'heure arrive (on avance la date en base) : l'accès est donné et la personne prévenue.
            with sqlite3.connect(db) as connection:
                connection.execute('UPDATE nathgpt_role_grants SET grant_at=?', (time.time() - 1,))
            notices = (await alice.get('/api/notices')).json()['notices']
            assert [n['role'] for n in notices] == ['is_admin']
            assert (await alice.get('/api/auth/me')).json()['account']['is_admin'] is True
            assert pushed[-1]['view'] == 'admin'
            assert (await admin.get('/api/admin/grants')).json()['grants'] == []

            # Une programmation peut être annulée avant l'heure.
            planned = (await admin.post('/api/admin/grants', json={'account_key': 'alice', 'role': 'cricut', 'grant_at': later})).json()
            assert (await admin.delete(f"/api/admin/grants/{planned['grant']['id']}")).status_code == 200
            assert (await admin.delete(f"/api/admin/grants/{planned['grant']['id']}")).status_code == 404

    run(scenario())


def test_stop_and_release(tmp_path):
    calls = []

    def vm(request):
        calls.append((request.url.path, json.loads(request.content or b'{}')))
        if request.url.path == '/v1/ask':
            async def never_ending():
                yield b': ok\n\n'
                await asyncio.sleep(30)
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=StreamAsync(never_ending()))
        if request.url.path == '/v1/cancel':
            return httpx.Response(200, json={'ok': True, 'cancelled': True})
        if request.url.path == '/admin/release':
            return httpx.Response(200, json={'ok': True, 'released': True, 'was': 'texte'})
        return httpx.Response(404)

    class StreamAsync(httpx.AsyncByteStream):
        def __init__(self, generator):
            self.generator = generator

        async def __aiter__(self):
            async for chunk in self.generator:
                yield chunk

    async def scenario():
        app, admin, alice, _ = await setup(tmp_path, httpx.MockTransport(vm))
        async with closing(admin, alice):
            pending = asyncio.create_task(alice.post('/api/chat', json={'prompt': 'Salut', 'conversation_id': 'conversation_1', 'request_id': 'reponse_1', 'stream': True}))
            for _ in range(100):
                if any(path == '/v1/ask' for path, _ in calls):
                    break
                await asyncio.sleep(0.01)
            stopped = (await alice.post('/api/chat/stop', json={'request_id': 'reponse_1'})).json()
            assert stopped == {'ok': True, 'cancelled': True}
            pending.cancel()
            assert ('/v1/cancel', {'conversation_id': 'conversation_1'}) in calls
            # Un autre compte ne peut pas arrêter la réponse d'alice.
            assert (await admin.post('/api/chat/stop', json={'request_id': 'reponse_1'})).json()['cancelled'] is False

            assert (await alice.post('/api/admin/release')).status_code == 403
            assert (await admin.post('/api/admin/release')).json() == {'ok': True, 'released': True, 'was': 'texte'}

    run(scenario())
