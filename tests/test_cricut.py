"""Mode Cricut côté site : accès par la case cricut, proxy vers la VM, notification push à la fin."""

import asyncio
import json
import sqlite3
import sys
import types

import httpx

from server import Settings, create_app

PASSWORD = 'motdepasse-solide'
TOKEN = 'jeton-api-' + 'x' * 40
JOB = 'a' * 32


def run(coroutine):
    return asyncio.run(coroutine)


def vm_transport(calls):
    def handler(request):
        calls.append(request)
        path, owner = request.url.path, request.url.params.get('owner')
        assert request.headers['authorization'] == f'Bearer {TOKEN}'
        if path == '/cricut/jobs' and request.method == 'POST':
            body = json.loads(request.content)
            assert body['owner'] == 'nath' and body['callback_url'] == 'http://testserver/api/cricut/callback'
            return httpx.Response(200, json={'ok': True, 'job': {'id': JOB, 'phase': 'waiting'}})
        if path == '/cricut/jobs':
            return httpx.Response(200, json={'ok': True, 'jobs': [{'id': JOB, 'owner': owner}]})
        if path == f'/cricut/jobs/{JOB}/files/sticker_01.png':
            return httpx.Response(200, headers={'content-type': 'image/png'}, content=b'PNG' + request.url.params.get('download', '').encode())
        if path == f'/cricut/jobs/{JOB}/zip':
            return httpx.Response(200, headers={'content-type': 'application/zip'}, content=b'PK')
        if path == f'/cricut/jobs/{JOB}':
            return httpx.Response(200, json={'ok': True, 'job': {'id': JOB, 'owner': owner}})
        return httpx.Response(404, json={'ok': False, 'error': {'message': 'introuvable'}})
    return httpx.MockTransport(handler)


def test_cricut_routes_and_access(tmp_path):
    calls = []

    async def scenario():
        db = tmp_path / 'db.sqlite3'
        app = create_app(Settings('https://vm.example.com', TOKEN, db), transport=vm_transport(calls))
        nath = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        async with nath, alice:
            await nath.post('/api/auth/signup', json={'pseudo': 'nath', 'password': PASSWORD})
            await alice.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            assert (await nath.get('/api/cricut/jobs')).status_code == 403
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE nathgpt_accounts SET cricut=1 WHERE key='nath'")
            assert (await nath.get('/api/auth/me')).json()['account']['cricut'] is True
            assert (await alice.get('/api/auth/me')).json()['account']['cricut'] is False

            created = await nath.post('/api/cricut/jobs', json={'image': 'iVBORw0KGgo=', 'type': 'image/png', 'name': 'planche.png'})
            assert created.status_code == 200 and created.json()['job']['id'] == JOB
            assert (await nath.post('/api/cricut/jobs', json={'image': 'x', 'type': 'image/heic'})).status_code == 400
            assert (await nath.get('/api/cricut/jobs')).json()['jobs'][0]['owner'] == 'nath'
            preview = await nath.get(f'/api/cricut/jobs/{JOB}/files/sticker_01.png')
            assert preview.content == b'PNG' and 'content-disposition' not in preview.headers
            download = await nath.get(f'/api/cricut/jobs/{JOB}/files/sticker_01.png?download=1')
            assert download.content == b'PNG1' and 'attachment' in download.headers['content-disposition']
            assert (await nath.get(f'/api/cricut/jobs/{JOB}/zip')).content == b'PK'
            assert (await nath.get(f'/api/cricut/jobs/{JOB}/files/..%2Fjob.json')).status_code == 404
            assert (await nath.get('/api/cricut/jobs/pas-un-id')).status_code == 404
            assert (await nath.get(f'/api/cricut/jobs/{"b" * 32}')).status_code == 404
            for path in ('/api/cricut/jobs', f'/api/cricut/jobs/{JOB}', f'/api/cricut/jobs/{JOB}/zip'):
                assert (await alice.get(path)).status_code == 403
        assert all(call.url.params['owner'] == 'nath' for call in calls)

    run(scenario())


def test_callback_sends_push_once(tmp_path, monkeypatch):
    pushed = []
    fake = types.ModuleType('pywebpush')

    class WebPushException(Exception):
        def __init__(self, message, response=None):
            super().__init__(message)
            self.response = response

    def webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl):
        if subscription_info['endpoint'].endswith('/perime'):
            raise WebPushException('gone', response=types.SimpleNamespace(status_code=410))
        pushed.append((subscription_info['endpoint'], json.loads(data), vapid_claims['sub']))
    fake.webpush, fake.WebPushException = webpush, WebPushException
    monkeypatch.setitem(sys.modules, 'pywebpush', fake)

    async def scenario():
        db = tmp_path / 'db.sqlite3'
        settings = Settings('https://vm.example.com', TOKEN, db, vapid_public='BPublic', vapid_private='private')
        app = create_app(settings, transport=vm_transport([]))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            await client.post('/api/auth/signup', json={'pseudo': 'nath', 'password': PASSWORD})
            assert (await client.get('/api/push/key')).json() == {'key': 'BPublic'}
            for endpoint in ('https://push.example/appareil', 'https://push.example/perime'):
                ok = await client.post('/api/push/subscribe', json={'endpoint': endpoint, 'keys': {'p256dh': 'BKey_1', 'auth': 'auth-1'}})
                assert ok.status_code == 200
            bad = await client.post('/api/push/subscribe', json={'endpoint': 'http://pas-https', 'keys': {'p256dh': 'a', 'auth': 'b'}})
            assert bad.status_code == 400

            job = {'id': JOB, 'owner': 'nath', 'phase': 'stickers', 'completed': 3}
            assert (await client.post('/api/cricut/callback', json=job)).status_code == 401
            headers = {'authorization': f'Bearer {TOKEN}'}
            assert (await client.post('/api/cricut/callback', json=job, headers=headers)).status_code == 200
            assert pushed == []
            finished = {**job, 'phase': 'finished', 'completed': 24}
            await client.post('/api/cricut/callback', json=finished, headers=headers)
            await client.post('/api/cricut/callback', json=finished, headers=headers)
        assert len(pushed) == 1
        endpoint, payload, subject = pushed[0]
        assert endpoint == 'https://push.example/appareil' and payload['view'] == 'cricut' and '24 stickers' in payload['body']
        assert subject == 'http://testserver'
        remaining = await app.state.store.list_push_subscriptions('nath')
        assert [sub['endpoint'] for sub in remaining] == ['https://push.example/appareil']

    run(scenario())
