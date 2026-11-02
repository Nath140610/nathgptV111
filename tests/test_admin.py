"""Page Admin : réservée aux comptes is_admin, proxy vers les routes /admin/* de la VM."""

import asyncio
import sqlite3

import httpx

from server import Settings, create_app
from services.store import SupabaseStore

PASSWORD = 'motdepasse-solide'
TOKEN = 'jeton-api-' + 'x' * 40


def run(coroutine):
    return asyncio.run(coroutine)


def test_admin_routes(tmp_path):
    calls = []

    def upstream(request):
        calls.append(request)
        assert request.headers['authorization'] == f'Bearer {TOKEN}'
        if request.url.path == '/admin/status':
            return httpx.Response(200, json={'ok': True, 'busy': False, 'chromium': True, 'uptime': 42})
        if request.url.path == '/admin/screenshot':
            return httpx.Response(200, headers={'content-type': 'image/jpeg'}, content=b'\xff\xd8JPEG')
        if request.url.path == '/admin/logs':
            return httpx.Response(200, json={'ok': True, 'lines': ['a', 'b']})
        if request.url.path == '/admin/restart' and request.method == 'POST':
            return httpx.Response(200, json={'ok': True, 'restarting': True})
        return httpx.Response(404)

    async def scenario():
        db = tmp_path / 'db.sqlite3'
        app = create_app(Settings('https://vm.example.com', TOKEN, db), transport=httpx.MockTransport(upstream))
        admin = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        user = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        anonymous = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        async with admin, user, anonymous:
            await admin.post('/api/auth/signup', json={'pseudo': 'nath', 'password': PASSWORD})
            await user.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            assert (await admin.get('/api/auth/me')).json()['account']['is_admin'] is False
            assert (await admin.get('/api/admin/status')).status_code == 403
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE nathgpt_accounts SET is_admin=1 WHERE key='nath'")
            assert (await admin.get('/api/auth/me')).json()['account']['is_admin'] is True

            status = (await admin.get('/api/admin/status')).json()
            assert status['online'] is True and status['vm']['chromium'] is True
            shot = await admin.get('/api/admin/screenshot')
            assert shot.content == b'\xff\xd8JPEG' and shot.headers['cache-control'] == 'no-store'
            assert (await admin.get('/api/admin/logs')).json()['lines'] == ['a', 'b']
            assert (await admin.post('/api/admin/restart')).json() == {'ok': True}
            evil = await admin.post('/api/admin/restart', headers={'origin': 'https://pirate.example'})
            assert evil.status_code == 403

            for path in ('/api/admin/status', '/api/admin/screenshot', '/api/admin/logs'):
                assert (await user.get(path)).status_code == 403
                assert (await anonymous.get(path)).status_code == 401
            assert (await user.post('/api/admin/restart')).status_code == 403
        assert sum(call.url.path == '/admin/restart' for call in calls) == 1

    run(scenario())


def test_admin_status_when_vm_offline(tmp_path):
    def upstream(_request):
        raise httpx.ConnectError('VM éteinte')

    async def scenario():
        db = tmp_path / 'db.sqlite3'
        app = create_app(Settings('https://vm.example.com', TOKEN, db), transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            await client.post('/api/auth/signup', json={'pseudo': 'nath', 'password': PASSWORD})
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE nathgpt_accounts SET is_admin=1 WHERE key='nath'")
            status = (await client.get('/api/admin/status')).json()
            assert status['online'] is False and 'ne répond pas' in status['message']
            assert (await client.get('/api/admin/screenshot')).status_code == 502

    run(scenario())


def test_supabase_is_admin():
    def handler(request):
        key = request.url.params['key']
        if key == 'eq.nath':
            return httpx.Response(200, json=[{'is_admin': True}])
        if key == 'eq.ancien':  # colonne absente : schema.sql pas encore relancé
            return httpx.Response(400, json={'code': '42703'})
        return httpx.Response(200, json=[{'is_admin': False}])

    async def scenario():
        store = SupabaseStore('https://exemple.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handler))
        assert await store.is_admin('nath') is True
        assert await store.is_admin('alice') is False
        assert await store.is_admin('ancien') is False

    run(scenario())
