"""Images générées : reçues de l'API, enregistrées, servies uniquement à leur propriétaire."""

import asyncio
import base64
import io
import json
import os
import time

import httpx
from PIL import Image

from server import Settings, create_app
from services.store import SupabaseStore, image_folder

PASSWORD = 'motdepasse-solide'


def big_png() -> bytes:
    # Bruit aléatoire : le PNG dépasse 1 Mo, comme une vraie image ChatGPT.
    image = Image.frombytes('RGB', (700, 700), os.urandom(700 * 700 * 3))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def run(coroutine):
    return asyncio.run(coroutine)


def test_image_stream_saved_and_private(tmp_path):
    png = big_png()
    assert len(png) > 1_000_000
    encoded = base64.b64encode(png).decode()
    sent = []

    vm_storage = {}

    def upstream(request):
        # Fausse VM : /v1/ask génère l'image, /storage/images la garde (4 h sur la vraie VM).
        if request.url.path.startswith('/storage/images/'):
            if request.method == 'PUT':
                vm_storage[request.url.path] = request.content
                return httpx.Response(200, json={'ok': True})
            data = vm_storage.get(request.url.path)
            return httpx.Response(200, content=data) if data else httpx.Response(404)
        sent.append(json.loads(request.content))
        image_event = json.dumps({'mime_type': 'image/png', 'filename': 'image_1.png', 'base64': encoded, 'b64_json': encoded})
        body = f'event: image\ndata: {image_event}\n\nevent: done\ndata: {{"type":"image"}}\n\n'.encode()
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=body)

    async def scenario():
        app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=httpx.MockTransport(upstream))
        alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        bob = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        async with alice, bob:
            await alice.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            await bob.post('/api/auth/signup', json={'pseudo': 'bob', 'password': PASSWORD})
            response = await alice.post('/api/chat', json={'prompt': 'un chat', 'conversation_id': 'conversation_1', 'stream': True, 'mode': 'Image'})
            assert response.status_code == 200
            assert sent[0]['response_type'] == 'image'
            image_line = response.text.split('event: image\ndata: ', 1)[1].split('\n', 1)[0]
            event = json.loads(image_line)
            assert event['url'].startswith('/api/images/') and event['url'].endswith('.png')
            assert 'base64' not in response.text  # le navigateur reçoit un lien, pas des Mo de base64
            served = await alice.get(event['url'])
            assert served.status_code == 200 and served.content == png
            assert served.headers['content-type'] == 'image/png'
            assert (await bob.get(event['url'])).status_code == 404
            assert (await alice.get('/api/images/..%2Fdb.sqlite3')).status_code == 404
            assert list(vm_storage) == [f"/storage/images/{image_folder('alice')}/{event['url'].rsplit('/', 1)[1]}"]

    run(scenario())


def test_invalid_image_is_rejected(tmp_path):
    def upstream(_request):
        bad = json.dumps({'mime_type': 'image/png', 'base64': base64.b64encode(b'<html>pas une image</html>').decode()})
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=f'event: image\ndata: {bad}\n\n'.encode())

    async def scenario():
        app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            response = await client.post('/api/chat', json={'prompt': 'x', 'conversation_id': 'conversation_1', 'stream': True})
            assert 'event: error' in response.text and 'image_error' in response.text

    run(scenario())


def test_supabase_storage_paths():
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, content=b'PNGDATA')
        return httpx.Response(200, json={'Key': 'ok'})

    async def scenario():
        store = SupabaseStore('https://exemple.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handler))
        await store.save_image('élodie', 'a' * 32 + '.png', b'PNGDATA', 'image/png')
        assert await store.load_image('élodie', 'a' * 32 + '.png') == b'PNGDATA'
        upload, download = calls
        expected = f"/storage/v1/object/nathgpt-images/{image_folder('élodie')}/{'a' * 32}.png"
        assert upload.url.path == expected and download.url.path == expected
        assert upload.headers['content-type'] == 'image/png'
        assert upload.headers['apikey'] == 'sb_secret_test'

    run(scenario())


def test_sqlite_images_deleted_after_one_day(tmp_path):
    from services.store import IMAGE_TTL_SECONDS, SQLiteStore

    async def scenario():
        store = SQLiteStore(tmp_path / 'db.sqlite3')
        await store.save_image('alice', 'a' * 32 + '.png', b'vieille', 'image/png')
        await store.save_image('alice', 'b' * 32 + '.png', b'recente', 'image/png')
        old = store._image_path('alice', 'a' * 32 + '.png')
        past = time.time() - IMAGE_TTL_SECONDS - 60
        os.utime(old, (past, past))
        assert await store.purge_images() == 1
        assert await store.load_image('alice', 'a' * 32 + '.png') is None
        assert await store.load_image('alice', 'b' * 32 + '.png') == b'recente'

    run(scenario())


def test_supabase_purge_expired_images():
    calls = []
    expired = [{'name': f'{image_folder("alice")}/{"c" * 32}.png'}, {'name': f'{image_folder("bob")}/{"d" * 32}.jpg'}]

    def handler(request):
        calls.append(request)
        if request.url.path == '/rest/v1/rpc/nathgpt_expired_images':
            assert json.loads(request.content) == {'p_limit': 1000}
            return httpx.Response(200, json=expired if len(calls) == 1 else [])
        assert request.method == 'DELETE' and request.url.path == '/storage/v1/object/nathgpt-images'
        return httpx.Response(200, json=[])

    async def scenario():
        store = SupabaseStore('https://exemple.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handler))
        assert await store.purge_images() == 2
        rpc, delete = calls
        assert json.loads(delete.content) == {'prefixes': [row['name'] for row in expired]}
        assert delete.headers['apikey'] == 'sb_secret_test'

    run(scenario())


def test_purge_runs_at_startup(tmp_path):
    from services.store import SQLiteStore
    seen = []

    async def fake_purge(self):
        seen.append(True)
        return 0

    async def scenario():
        original = SQLiteStore.purge_images
        SQLiteStore.purge_images = fake_purge
        try:
            app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'))
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0.05)
        finally:
            SQLiteStore.purge_images = original
        assert seen

    run(scenario())


def test_supabase_creates_missing_bucket():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/storage/v1/bucket':
            assert json.loads(request.content)['public'] is False
            return httpx.Response(200, json={'name': 'nathgpt-images'})
        if len(calls) == 1:  # premier envoi : le bucket n'existe pas encore
            return httpx.Response(400, json={'statusCode': '404', 'error': 'Bucket not found', 'message': 'Bucket not found'})
        return httpx.Response(200, json={'Key': 'ok'})

    async def scenario():
        store = SupabaseStore('https://exemple.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handler))
        await store.save_image('alice', 'a' * 32 + '.png', b'PNG', 'image/png')
        path = f"/storage/v1/object/nathgpt-images/{image_folder('alice')}/{'a' * 32}.png"
        assert calls == [('POST', path), ('POST', '/storage/v1/bucket'), ('POST', path)]

    run(scenario())


def test_image_shown_even_if_storage_fails(tmp_path):
    png = big_png()
    encoded = base64.b64encode(png).decode()

    def upstream(request):
        if request.url.path.startswith('/storage/images/'):
            return httpx.Response(507, json={'ok': False})  # disque de la VM plein
        body = f'event: image\ndata: {json.dumps({"mime_type": "image/png", "base64": encoded})}\n\nevent: done\ndata: {{"type":"image"}}\n\n'.encode()
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=body)

    async def scenario():
        app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            response = await client.post('/api/chat', json={'prompt': 'un chat', 'conversation_id': 'conversation_1', 'stream': True, 'mode': 'Image'})
            assert 'image_error' not in response.text
            event = json.loads(response.text.split('event: image\ndata: ', 1)[1].split('\n', 1)[0])
            served = await client.get(event['url'])
            assert served.status_code == 200 and served.content == png

    run(scenario())


def test_each_image_costs_five_cents(tmp_path):
    import server
    png = big_png()
    encoded = base64.b64encode(png).decode()

    def upstream(_request):
        events = ''.join(f'event: image\ndata: {json.dumps({"mime_type": "image/png", "base64": encoded})}\n\n' for _ in range(2))
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=(events + 'event: done\ndata: {"type":"image"}\n\n').encode())

    async def scenario():
        app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            response = await client.post('/api/chat', json={'prompt': 'deux chats', 'conversation_id': 'conversation_1', 'stream': True, 'mode': 'Image'})
            done = json.loads(response.text.split('event: done\ndata: ', 1)[1].split('\n', 1)[0])
            assert done['account_tokens_used'] == 2 * server.IMAGE_TOKENS
            tokens = (await client.get('/api/auth/me')).json()['account']['tokens_used']
            assert tokens == 2 * server.IMAGE_TOKENS
            assert round(tokens * server.PRICE_PER_TOKEN_EUR, 2) == 0.10

    run(scenario())
