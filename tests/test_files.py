"""Fichiers joints : envoyés par le navigateur, vérifiés, puis transmis à l'API NathGPT."""

import asyncio
import base64
import json

import httpx

from server import Settings, create_app

PASSWORD = 'motdepasse-solide'


def run(coroutine):
    return asyncio.run(coroutine)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def make_site(tmp_path, sent):
    def upstream(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              content=b'event: delta\ndata: {"text":"Lu !"}\n\nevent: done\ndata: {}\n\n')
    app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=httpx.MockTransport(upstream))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')


def test_files_forwarded_to_api(tmp_path):
    sent = []

    async def scenario():
        async with make_site(tmp_path, sent) as client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            big = b'%PDF-' + b'x' * (2 * 1024 * 1024)  # plus gros que l'ancienne limite de 64 Ko
            files = [{'name': 'cours.pdf', 'type': 'application/pdf', 'base64': b64(big)},
                     {'name': 'notes.txt', 'type': 'text/plain', 'base64': b64(b'bonjour')}]
            response = await client.post('/api/chat', json={'prompt': 'Résume', 'conversation_id': 'conversation_1', 'stream': True, 'files': files})
            assert response.status_code == 200 and 'Lu !' in response.text
            assert sent[0]['files'] == [
                {'filename': 'cours.pdf', 'mime_type': 'application/pdf', 'base64': b64(big)},
                {'filename': 'notes.txt', 'mime_type': 'text/plain', 'base64': b64(b'bonjour')},
            ]
            await client.post('/api/chat', json={'prompt': 'Salut', 'conversation_id': 'conversation_1', 'stream': True})
            assert 'files' not in sent[1]

    run(scenario())


def test_bad_files_rejected(tmp_path):
    sent = []

    async def scenario():
        async with make_site(tmp_path, sent) as client:
            await client.post('/api/auth/signup', json={'pseudo': 'alice', 'password': PASSWORD})
            cases = [
                ([{'name': 'a.txt', 'base64': b64(b'a')}] * 6, 400),
                ([{'name': 'a.txt', 'base64': '%%%pas du base64'}], 400),
                ([{'name': 'vide.txt', 'base64': ''}], 400),
                ([{'name': 'gros.bin', 'base64': b64(b'x' * (15 * 1024 * 1024 + 1))}], 413),
                ('pas une liste', 400),
            ]
            for files, status in cases:
                response = await client.post('/api/chat', json={'prompt': 'x', 'conversation_id': 'conversation_1', 'stream': True, 'files': files})
                assert response.status_code == status, (files if isinstance(files, str) else files[0]['name'], response.text)
            assert sent == []

    run(scenario())
