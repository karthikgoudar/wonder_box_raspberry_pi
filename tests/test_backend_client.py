"""Tests for services/backend_client.py against a local fake backend."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from services.backend_client import STRIP_BYTES, BackendClient, BackendError

TOKEN = "test-device-token"
STRIP = b"\x1d\x76\x30\x00\x30\x00\x18\x00" + b"\x00" * (STRIP_BYTES - 8)


class FakeBackend(BaseHTTPRequestHandler):
    # per-test knobs, set on the class by the fixture
    submit_failures = []  # status codes to return before succeeding
    requests_seen = []
    print_payload = STRIP * 16

    def log_message(self, *a):
        pass

    def _send(self, status, body, ctype="application/json", headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "healthy"})
        if self.path == "/storage/stickers/x_print.bin":
            return self._send(200, self.print_payload, "application/octet-stream")
        if self.path == "/sticker/job-1/stream":
            frames = (
                'event: status\ndata: {"state": "processing"}\n\n'
                ": keepalive\n\n"
                'event: progress\ndata: {"step": "transcribing"}\n\n'
                'event: text\ndata: {"text": "a penguin", "language": "en"}\n\n'
                'event: done\ndata: {"sticker_id": "s1", "print_url": "/storage/stickers/x_print.bin"}\n\n'
            ).encode()
            return self._send(200, frames, "text/event-stream")
        if self.path == "/sticker/job-err/stream":
            frames = b'event: error\ndata: {"message": "boom", "code": "GEN_FAIL"}\n\n'
            return self._send(200, frames, "text/event-stream")
        self._send(404, {"detail": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        FakeBackend.requests_seen.append((self.path, dict(self.headers), body))
        if self.headers.get("X-Device-Token") != TOKEN:
            return self._send(401, {"detail": "Device credentials required"})
        if FakeBackend.submit_failures:
            code = FakeBackend.submit_failures.pop(0)
            return self._send(code, {"detail": "nope", "code": "X"}, headers={"Retry-After": "0"})
        if self.path.startswith("/sticker/submit?mode=direct"):
            return self._send(200, {
                "status": "done", "job_id": "job-1", "sticker_id": "s1",
                "text": "a penguin", "language": "en",
                "image_url": "http://h/storage/stickers/x.png",
                "print_url": "/storage/stickers/x_print.bin",
                "print_png_url": None,
            })
        if self.path.startswith("/sticker/submit?mode=stream"):
            return self._send(200, {"job_id": "job-1"})
        self._send(404, {"detail": "not found"})


@pytest.fixture
def server():
    FakeBackend.submit_failures = []
    FakeBackend.requests_seen = []
    FakeBackend.print_payload = STRIP * 16
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeBackend)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "rec.wav"
    p.write_bytes(b"RIFF....WAVEfmt fake")
    return str(p)


def client(url, **kw):
    kw.setdefault("backoff_base", 0)
    return BackendClient(base_url=url, device_token=TOKEN, child_id="7", **kw)


def test_requires_config(monkeypatch):
    monkeypatch.delenv("BACKEND_URL", raising=False)
    monkeypatch.delenv("DEVICE_TOKEN", raising=False)
    with pytest.raises(ValueError):
        BackendClient()
    with pytest.raises(ValueError):
        BackendClient(base_url="http://x")


def test_reads_env(monkeypatch):
    monkeypatch.setenv("BACKEND_URL", "http://env:8000/")
    monkeypatch.setenv("DEVICE_TOKEN", "t")
    monkeypatch.setenv("CHILD_ID", "9")
    c = BackendClient()
    assert (c.base_url, c.device_token, c.child_id) == ("http://env:8000", "t", "9")


def test_health(server):
    assert client(server).health() is True
    assert client("http://127.0.0.1:1").health() is False


def test_direct_submit_sends_token_child_and_audio(server, wav):
    r = client(server).submit_sticker(wav)
    assert r.job_id == "job-1" and r.text == "a penguin"
    assert r.print_url == "/storage/stickers/x_print.bin"
    path, headers, body = FakeBackend.requests_seen[0]
    assert path == "/sticker/submit?mode=direct"
    assert headers["X-Device-Token"] == TOKEN
    assert b'name="child_id"' in body and b"\r\n\r\n7\r\n" in body
    assert b'name="audio"; filename="rec.wav"' in body
    assert b"RIFF....WAVEfmt fake" in body


def test_bad_token_is_not_retried(server, wav):
    c = BackendClient(base_url=server, device_token="wrong", child_id="7", backoff_base=0)
    with pytest.raises(BackendError) as ei:
        c.submit_sticker(wav)
    assert ei.value.status_code == 401
    assert len(FakeBackend.requests_seen) == 1


def test_retries_503_then_succeeds(server, wav):
    FakeBackend.submit_failures = [503, 429]
    r = client(server).submit_sticker(wav)
    assert r.job_id == "job-1"
    assert len(FakeBackend.requests_seen) == 3


def test_500_pipeline_error_not_retried(server, wav):
    FakeBackend.submit_failures = [500]
    with pytest.raises(BackendError) as ei:
        client(server).submit_sticker(wav)
    assert ei.value.status_code == 500 and ei.value.code == "X"
    assert len(FakeBackend.requests_seen) == 1


def test_gives_up_after_max_retries(server, wav):
    FakeBackend.submit_failures = [503] * 10
    with pytest.raises(BackendError) as ei:
        client(server, max_retries=2).submit_sticker(wav)
    assert ei.value.status_code == 503
    assert len(FakeBackend.requests_seen) == 3


def test_connection_refused_raises(wav):
    with pytest.raises(BackendError) as ei:
        client("http://127.0.0.1:1", max_retries=1).submit_sticker(wav)
    assert ei.value.status_code is None


def test_missing_child_id(server, wav):
    c = BackendClient(base_url=server, device_token=TOKEN, child_id="")
    with pytest.raises(ValueError):
        c.submit_sticker(wav)


def test_stream_mode_events(server, wav):
    events = list(client(server).submit_sticker_stream(wav))
    names = [e for e, _ in events]
    assert names == ["job", "status", "progress", "text", "done"]
    assert events[-1][1]["sticker_id"] == "s1"
    assert FakeBackend.requests_seen[0][0] == "/sticker/submit?mode=stream"


def test_stream_error_event_raises(server):
    with pytest.raises(BackendError) as ei:
        list(client(server).stream_events("job-err"))
    assert ei.value.code == "GEN_FAIL"


def test_print_strips(server):
    strips = client(server).download_print_strips("/storage/stickers/x_print.bin")
    assert len(strips) == 16
    assert all(len(s) == 1160 and s.startswith(b"\x1d\x76") for s in strips)


def test_print_strips_rejects_bad_length(server):
    FakeBackend.print_payload = STRIP * 2 + b"\x00"
    with pytest.raises(BackendError):
        client(server).download_print_strips("/storage/stickers/x_print.bin")
