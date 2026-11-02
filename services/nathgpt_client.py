"""Client SSE pour l'API NathGPT V4. Aucun secret ne quitte ce module."""

from __future__ import annotations

import codecs
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: str


class SSEProtocolError(Exception):
    pass


class UpstreamStatusError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"NathGPT HTTP {status_code}")


class SSEParser:
    """Parse des octets SSE, y compris les lignes UTF-8 coupées entre paquets."""

    # Une image PNG arrive entière dans un seul événement (base64) : plusieurs Mo.
    MAX_FRAME = 40_000_000

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buffer = ""
        self._data: list[str] = []
        self._event = "message"
        self._explicit_event = False
        self._first_line = True

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        return self._consume(self._decoder.decode(chunk), final=False)

    def finish(self) -> list[SSEEvent]:
        return self._consume(self._decoder.decode(b"", final=True), final=True)

    def _dispatch(self) -> SSEEvent | None:
        result = SSEEvent(self._event, "\n".join(self._data)) if self._data or self._explicit_event else None
        self._data = []
        self._event = "message"
        self._explicit_event = False
        return result

    def _line(self, line: str) -> SSEEvent | None:
        if self._first_line:
            line = line.lstrip("\ufeff")
            self._first_line = False
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value or "message"
            self._explicit_event = True
        elif field == "data":
            self._data.append(value)
        return None

    def _consume(self, text: str, *, final: bool) -> list[SSEEvent]:
        self._buffer += text
        if len(self._buffer) + sum(map(len, self._data)) > self.MAX_FRAME:
            raise SSEProtocolError("SSE frame too large")
        events: list[SSEEvent] = []
        while True:
            positions = [position for position in (self._buffer.find("\r"), self._buffer.find("\n")) if position >= 0]
            if not positions:
                break
            position = min(positions)
            if self._buffer[position] == "\r" and position == len(self._buffer) - 1 and not final:
                break
            line = self._buffer[:position]
            length = 2 if self._buffer[position:position + 2] == "\r\n" else 1
            self._buffer = self._buffer[position + length:]
            event = self._line(line)
            if event is not None:
                events.append(event)
        if final:
            if self._buffer:
                event = self._line(self._buffer)
                if event is not None:
                    events.append(event)
                self._buffer = ""
            event = self._dispatch()
            if event is not None:
                events.append(event)
        return events


def _parse_data(data: str):
    if data == "[DONE]":
        return data
    try:
        return json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return data


def _text_value(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "delta", "content", "response", "value"):
            if key in value:
                return _text_value(value[key])
    return None


def _usage_data(payload) -> dict:
    if not isinstance(payload, dict):
        return {}
    usage = payload.get("usage", payload)
    if not isinstance(usage, dict):
        return {}
    total = usage.get("total_tokens")
    if total is None:
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        if all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (input_tokens, output_tokens)):
            total = input_tokens + output_tokens
    if isinstance(total, int) and not isinstance(total, bool) and 0 <= total <= 1_000_000_000:
        return {"total_tokens": total}
    return {}


def _image_data(payload) -> dict | None:
    """Image de l'API (champ base64, ou b64_json pour les anciennes versions)."""
    if not isinstance(payload, dict):
        return None
    encoded = payload.get("base64") or payload.get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        return None
    return {"base64": encoded, "mime_type": str(payload.get("mime_type") or "image/png"), "filename": str(payload.get("filename") or "image.png")}


def normalize_event(event: SSEEvent) -> tuple[str, dict] | None:
    """Convertit les variantes SSE usuelles en delta/replace/image/done/error."""
    payload = _parse_data(event.data)
    kind = event.event.lower().strip()
    if payload == "[DONE]":
        kind = "done"
    elif kind == "message" and isinstance(payload, dict):
        kind = str(payload.get("type") or payload.get("event") or ("delta" if _text_value(payload) is not None else "message")).lower()
    elif kind == "message" and isinstance(payload, str) and payload:
        kind = "delta"

    if kind in ("delta", "replace"):
        text = _text_value(payload)
        if text is None:
            return None
        return kind, {"text": text}
    if kind == "image":
        image = _image_data(payload)
        return ("image", image) if image else None
    if kind == "done":
        return "done", _usage_data(payload)
    if kind == "error":
        return "error", {"code": "upstream_error", "message": "NathGPT a interrompu la réponse."}
    return None


def validate_api_url(base_url: str) -> str:
    parts = urlsplit(base_url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("NATHGPT_API_URL invalide")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Une API distante doit utiliser HTTPS")
    base = base_url.rstrip("/")
    return base if base.endswith("/v1/ask") else base + "/v1/ask"


class NathGPTClient:
    def __init__(self, base_url: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.url = validate_api_url(base_url)
        self.token = token.strip()
        self.transport = transport

    async def open_stream(self, prompt: str, conversation_id: str, *, image: bool = False) -> tuple[httpx.AsyncClient, httpx.Response]:
        timeout = httpx.Timeout(connect=5, read=120, write=10, pool=5)
        client = httpx.AsyncClient(timeout=timeout, transport=self.transport, follow_redirects=False, trust_env=False)
        request = client.build_request(
            "POST", self.url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
            },
            json={"prompt": prompt, "conversation_id": conversation_id, "stream": True, **({"response_type": "image"} if image else {})},
        )
        try:
            response = await client.send(request, stream=True)
            if response.status_code != 200:
                status = response.status_code
                await response.aclose()
                raise UpstreamStatusError(status)
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type and "application/json" not in content_type:
                await response.aclose()
                raise SSEProtocolError("NathGPT returned an unsupported content type")
            return client, response
        except BaseException:
            await client.aclose()
            raise

    @staticmethod
    async def events(response: httpx.Response):
        if "application/json" in response.headers.get("content-type", ""):
            raw = await response.aread()
            if len(raw) > SSEParser.MAX_FRAME:
                raise SSEProtocolError("JSON response too large")
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise SSEProtocolError("Invalid JSON response") from None
            answer = payload.get("answer") if isinstance(payload, dict) else None
            if not isinstance(answer, str):
                raise SSEProtocolError("Missing answer in JSON response")
            for item in payload.get("images") or []:
                image = _image_data(item)
                if image:
                    yield "image", image
            yield "replace", {"text": answer}
            yield "done", _usage_data(payload)
            return
        parser = SSEParser()
        async for chunk in response.aiter_bytes():
            for event in parser.feed(chunk):
                normalized = normalize_event(event)
                if normalized:
                    yield normalized
                    if normalized[0] in ("done", "error"):
                        return
        for event in parser.finish():
            normalized = normalize_event(event)
            if normalized:
                yield normalized
                if normalized[0] in ("done", "error"):
                    return
