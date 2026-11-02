import asyncio
import json
from pathlib import Path

import httpx
from starlette.requests import Request

from server import Settings, create_app
from services.nathgpt_client import SSEEvent, SSEParser, NathGPTClient, normalize_event


def run(coroutine):
    return asyncio.run(coroutine)


def test_sse_fragments_and_replace():
    parser = SSEParser()
    raw = 'event: delta\r\ndata: {"text":"B"}\r\n\r\nevent: delta\ndata: {"text":"on"}\n\nevent: replace\ndata: {"text":"Bonjour 🌟"}\n\nevent: done\ndata: {}\n\n'.encode()
    events = []
    for byte in raw:
        events.extend(parser.feed(bytes([byte])))
    events.extend(parser.finish())
    normalized = [normalize_event(event) for event in events]
    assert normalized == [('delta', {'text': 'B'}), ('delta', {'text': 'on'}), ('replace', {'text': 'Bonjour 🌟'}), ('done', {})]


def test_usage_in_done_event():
    event = SSEEvent('done', '{"usage":{"prompt_tokens":3,"completion_tokens":7}}')
    assert normalize_event(event) == ('done', {'total_tokens': 10})
    assert normalize_event(SSEEvent('done', '{"usage":{"total_tokens":12}}')) == ('done', {'total_tokens': 12})
    assert normalize_event(SSEEvent('done', '{"usage":{"total_tokens":true}}')) == ('done', {})


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk

    async def aclose(self):
        self.closed = True


def mock_transport(status=200, chunks=None, content_type='text/event-stream'):
    requests = []
    streams = []

    def handler(request):
        requests.append(request)
        stream = ChunkStream(chunks or [b'event: delta\ndata: {"text":"Bonjour"}\n\nevent: done\ndata: {}\n\n'])
        streams.append(stream)
        return httpx.Response(status, headers={'content-type': content_type}, stream=stream)

    return httpx.MockTransport(handler), requests, streams


async def signup(client, pseudo='alice'):
    response = await client.post('/api/auth/signup', json={'pseudo': pseudo, 'password': 'motdepasse-solide'})
    assert response.status_code == 200, response.text
    return response


async def site_client(tmp_path: Path, transport):
    app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=transport)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')


def test_real_route_streams_normalizes_and_closes(tmp_path):
    async def scenario():
        chunks = [b'event: delta\ndata: {"text":"B"}\n\n', b'event: delta\ndata: {"text":"on"}\n\n', b'event: replace\ndata: {"text":"Bonjour"}\n\n', b'event: done\ndata: {}\n\n']
        transport, requests, streams = mock_transport(chunks=chunks)
        async with await site_client(tmp_path, transport) as client:
            assert (await signup(client)).status_code == 200
            response = await client.post('/api/chat', json={'prompt': 'Salut', 'conversation_id': 'conversation_1', 'stream': True})
            assert response.status_code == 200
            assert response.headers['content-type'].startswith('text/event-stream')
            assert 'event: delta\ndata: {"text":"B"}' in response.text
            assert 'event: replace\ndata: {"text":"Bonjour"}' in response.text
            assert 'event: done' in response.text
        assert streams[0].closed
        assert requests[0].headers['authorization'] == 'Bearer test-secret'
        assert json.loads(requests[0].content) == {'prompt': 'Salut', 'conversation_id': 'conversation_1', 'stream': True}

    run(scenario())


def test_two_sessions_cannot_share_conversation(tmp_path):
    async def scenario():
        transport, requests, _ = mock_transport()
        async with await site_client(tmp_path, transport) as alice, await site_client(tmp_path, transport) as bob:
            await signup(alice, 'alice')
            await signup(bob, 'bob')
            first = await alice.post('/api/chat', json={'prompt': 'Un', 'conversation_id': 'conversation_1', 'stream': True})
            denied = await bob.post('/api/chat', json={'prompt': 'Deux', 'conversation_id': 'conversation_1', 'stream': True})
            separate = await bob.post('/api/chat', json={'prompt': 'Deux', 'conversation_id': 'conversation_2', 'stream': True})
            assert first.status_code == 200 and separate.status_code == 200
            assert denied.status_code == 403
            assert len(requests) == 2

    run(scenario())


def test_same_account_keeps_conversation_after_login(tmp_path):
    async def scenario():
        transport, requests, _ = mock_transport()
        async with await site_client(tmp_path, transport) as client:
            await signup(client)
            first = await client.post('/api/chat', json={'prompt': 'Un', 'conversation_id': 'conversation_1', 'stream': True})
            await client.post('/api/session/logout')
            assert (await client.post('/api/auth/login', json={'pseudo': 'Alice', 'password': 'motdepasse-solide'})).status_code == 200
            second = await client.post('/api/chat', json={'prompt': 'Deux', 'conversation_id': 'conversation_1', 'stream': True})
            assert first.status_code == 200 and second.status_code == 200
            assert len(requests) == 2

    run(scenario())


def test_authentication_error_and_unavailable(tmp_path):
    async def scenario():
        transport, _, streams = mock_transport(status=401)
        async with await site_client(tmp_path, transport) as client:
            await signup(client)
            response = await client.post('/api/chat', json={'prompt': 'Salut', 'conversation_id': 'conversation_1', 'stream': True})
            assert response.status_code == 502
            assert 'test-secret' not in response.text
        assert streams[0].closed

        def unavailable(_request):
            raise httpx.ConnectError('unavailable')
        async with await site_client(tmp_path / 'second', httpx.MockTransport(unavailable)) as client:
            await signup(client)
            response = await client.post('/api/chat', json={'prompt': 'Salut', 'conversation_id': 'conversation_2', 'stream': True})
            assert response.status_code == 502

    run(scenario())


def test_current_json_api_response_is_displayed_without_fake_streaming(tmp_path):
    async def scenario():
        transport, _, _ = mock_transport(chunks=[b'{"answer":"Bonjour NathGPT","usage":{"total_tokens":17}}'], content_type='application/json')
        async with await site_client(tmp_path, transport) as client:
            await signup(client)
            response = await client.post('/api/chat', json={'prompt': 'Salut', 'conversation_id': 'conversation_1', 'stream': True})
            assert response.status_code == 200
            assert 'event: replace\ndata: {"text":"Bonjour NathGPT"}' in response.text
            done = json.loads(response.text.split('event: done\ndata: ', 1)[1].split('\n', 1)[0])
            assert done == {'total_tokens': 17, 'account_tokens_used': 17, 'usage_estimated': False}

    run(scenario())


def test_upstream_stream_closed_after_browser_cancel(tmp_path):
    async def scenario():
        transport, _, streams = mock_transport(chunks=[b'event: delta\ndata: {"text":"B"}\n\n'] * 100)
        app = create_app(Settings('http://127.0.0.1:18765', 'test-secret', tmp_path / 'db.sqlite3'), transport=transport)
        assert await app.state.store.create_account('alice', 'alice', 'scrypt:1:1:1$x$y')
        sid = await app.state.store.create_session('alice')
        body = json.dumps({'prompt': 'Salut', 'conversation_id': 'conversation_1', 'stream': True}).encode()
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        scope = {'type': 'http', 'method': 'POST', 'scheme': 'http', 'path': '/api/chat', 'root_path': '', 'query_string': b'', 'headers': [(b'content-type', b'application/json'), (b'cookie', f'nathgpt_backend_sid={sid}'.encode())], 'client': ('127.0.0.1', 1234), 'server': ('testserver', 80), 'http_version': '1.1'}
        request = Request(scope, receive)
        endpoint = next(route.endpoint for route in app.routes if getattr(route, 'path', '') == '/api/chat')
        response = await endpoint(request)
        assert b'event: delta' in await anext(response.body_iterator)
        await response.body_iterator.aclose()
        assert streams[0].closed
        assert app.state.gate.global_active == 0

    run(scenario())
