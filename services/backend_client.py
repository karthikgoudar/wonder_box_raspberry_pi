"""
backend_client.py: HTTP client for the WonderBox cloud backend.

Replaces the Pi's local Whisper + DALL-E pipeline. The Pi records a WAV,
uploads it here, and gets back URLs for the display image and the
pre-rendered thermal print payload.

Backend contract (wonderbox-backend, app/routes/sticker.py):

  POST /sticker/submit?mode=direct
      multipart: child_id (form), audio (file)
      header:    X-Device-Token
      200 -> {"status": "done", "job_id", "sticker_id", "text", "language",
              "image_url", "print_url", "print_png_url"}
      500 -> {"detail", "code"}   (pipeline failure)
      401/403/404/429 on auth, blocked device, unknown child, rate limit

  POST /sticker/submit?mode=stream  -> {"job_id": "..."}
  GET  /sticker/{job_id}/stream     -> SSE: status, progress, text,
                                       image_ready, done, error

  print_url points at a .bin made of 1,160-byte strips
  (8-byte ESC/POS GS v 0 header + 48 bytes x 24 rows of 1-bit pixels).

Configuration (environment or constructor args):
  BACKEND_URL    e.g. http://192.168.1.20:8000
  DEVICE_TOKEN   raw token from POST /device/register
  CHILD_ID       child profile id the backend requires on every submit

All calls are blocking. Callers on the pygame loop (ai_service, PI-03)
should run them on a worker thread, as the existing services already do.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Tuple
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

# ESC/POS strip geometry produced by the backend (see report section 1.4)
STRIP_HEADER_BYTES = 8
STRIP_BITMAP_BYTES = 48 * 24  # 384 dots wide = 48 bytes, 24 rows
STRIP_BYTES = STRIP_HEADER_BYTES + STRIP_BITMAP_BYTES  # 1,160

# Status codes worth retrying: the request never produced a sticker.
_RETRYABLE_STATUS = {429, 502, 503, 504}


class BackendError(Exception):
    """Any failure talking to the backend.

    status_code is None for network-level failures.
    code is the backend's machine-readable error code when it sent one.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


@dataclass
class StickerResult:
    job_id: str
    sticker_id: Optional[str]
    text: Optional[str]
    language: Optional[str]
    image_url: Optional[str]
    print_url: Optional[str]
    print_png_url: Optional[str]

    @classmethod
    def from_json(cls, job_id: str, data: dict) -> "StickerResult":
        return cls(
            job_id=job_id,
            sticker_id=data.get("sticker_id"),
            text=data.get("text"),
            language=data.get("language"),
            image_url=data.get("image_url"),
            print_url=data.get("print_url"),
            print_png_url=data.get("print_png_url"),
        )


class BackendClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        device_token: Optional[str] = None,
        child_id: Optional[str] = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 90.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = (base_url or os.getenv("BACKEND_URL") or "").rstrip("/")
        self.device_token = device_token or os.getenv("DEVICE_TOKEN") or ""
        self.child_id = child_id or os.getenv("CHILD_ID") or ""
        if not self.base_url:
            raise ValueError("BACKEND_URL is not set")
        if not self.device_token:
            raise ValueError("DEVICE_TOKEN is not set")

        self.timeout = (connect_timeout, read_timeout)
        self.max_retries = max(0, max_retries)
        self.backoff_base = backoff_base
        self.session = session or requests.Session()
        self.session.headers["X-Device-Token"] = self.device_token

    # ── public API ────────────────────────────────────────────────────────

    def health(self) -> bool:
        """True if GET /health answers 200. Never raises."""
        try:
            r = self.session.get(self._url("/health"), timeout=(self.timeout[0], 5))
            return r.status_code == 200
        except requests.RequestException as e:
            logger.warning("[backend] health check failed: %s", e)
            return False

    def submit_sticker(self, wav_path: str, child_id: Optional[str] = None) -> StickerResult:
        """Upload a WAV with mode=direct and block until the sticker is ready."""
        resp = self._post_audio(wav_path, child_id, mode="direct")
        data = self._json(resp)
        if data.get("status") != "done":
            raise BackendError(f"unexpected direct-mode payload: {data!r}", resp.status_code)
        result = StickerResult.from_json(data.get("job_id", ""), data)
        logger.info("[backend] sticker %s ready: %r", result.job_id, result.text)
        return result

    def submit_sticker_stream(
        self, wav_path: str, child_id: Optional[str] = None
    ) -> Iterator[Tuple[str, dict]]:
        """Upload a WAV with mode=stream and yield (event, data) SSE pairs.

        Ends after the 'done' event. An 'error' event raises BackendError.
        Use this to drive LCD state transitions (thinking, drawing, ...).
        """
        resp = self._post_audio(wav_path, child_id, mode="stream")
        job_id = self._json(resp).get("job_id")
        if not job_id:
            raise BackendError("stream submit returned no job_id", resp.status_code)
        logger.info("[backend] job %s submitted (stream)", job_id)
        yield ("job", {"job_id": job_id})
        yield from self.stream_events(job_id)

    def stream_events(self, job_id: str) -> Iterator[Tuple[str, dict]]:
        """Yield (event, data) from GET /sticker/{job_id}/stream until done/error."""
        try:
            resp = self.session.get(
                self._url(f"/sticker/{job_id}/stream"),
                stream=True,
                timeout=self.timeout,
                headers={"Accept": "text/event-stream"},
            )
        except requests.RequestException as e:
            raise BackendError(f"stream connect failed: {e}", retryable=True) from e

        with resp:
            self._raise_for_status(resp)
            for event, data in _parse_sse(resp.iter_lines(decode_unicode=True)):
                if event == "error":
                    raise BackendError(
                        data.get("message", "pipeline error"),
                        code=data.get("code"),
                    )
                yield event, data
                if event == "done":
                    return
        raise BackendError(f"stream for job {job_id} ended without a done event")

    def download(self, url: str) -> bytes:
        """GET an asset (image_url, print_url, ...) with retries."""
        full = self._url(url)
        resp = self._with_retries(
            "download", lambda: self.session.get(full, timeout=self.timeout)
        )
        return resp.content

    def download_print_strips(self, print_url: str) -> list:
        """Download the .bin print payload and split it into 1,160-byte strips.

        Each strip is a self-contained ESC/POS GS v 0 command that can be
        written to the printer followed by a short pause (~80 ms).
        """
        payload = self.download(print_url)
        if not payload or len(payload) % STRIP_BYTES != 0:
            raise BackendError(
                f"print payload is {len(payload)} bytes, not a multiple of {STRIP_BYTES}"
            )
        strips = [payload[i : i + STRIP_BYTES] for i in range(0, len(payload), STRIP_BYTES)]
        for n, strip in enumerate(strips):
            if strip[:2] != b"\x1d\x76":
                raise BackendError(f"strip {n} lacks a GS v 0 header")
        return strips

    # ── internals ─────────────────────────────────────────────────────────

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return urljoin(self.base_url + "/", path_or_url.lstrip("/"))

    def _post_audio(self, wav_path: str, child_id: Optional[str], mode: str) -> requests.Response:
        child = child_id or self.child_id
        if not child:
            raise ValueError("child_id is required (pass it or set CHILD_ID)")
        path = Path(wav_path)
        audio_bytes = path.read_bytes()  # read once; retries reuse the bytes
        url = self._url("/sticker/submit")

        def send():
            return self.session.post(
                url,
                params={"mode": mode},
                data={"child_id": child},
                files={"audio": (path.name, audio_bytes, "audio/wav")},
                timeout=self.timeout,
            )

        return self._with_retries(f"submit({mode})", send, retry_read_timeout=False)

    def _with_retries(self, label: str, send, retry_read_timeout: bool = True) -> requests.Response:
        """Run send() with exponential backoff.

        Retries connection failures and 429/502/503/504. A read timeout on a
        submit is NOT retried: the backend may already be generating, and a
        retry would pay for a second image.
        """
        attempt = 0
        while True:
            try:
                resp = send()
            except requests.ConnectionError as e:
                err = BackendError(f"{label}: connection failed: {e}", retryable=True)
            except requests.Timeout as e:
                is_connect = isinstance(e, requests.ConnectTimeout)
                err = BackendError(
                    f"{label}: timed out: {e}",
                    retryable=is_connect or retry_read_timeout,
                )
            except requests.RequestException as e:
                err = BackendError(f"{label}: request failed: {e}")
            else:
                if resp.status_code < 400:
                    return resp
                try:
                    self._raise_for_status(resp)
                except BackendError as be:
                    err = be

            if not err.retryable or attempt >= self.max_retries:
                logger.error("[backend] %s failed after %d attempt(s): %s", label, attempt + 1, err)
                raise err
            delay = self._retry_delay(attempt, getattr(err, "_retry_after", None))
            logger.warning(
                "[backend] %s attempt %d failed (%s); retrying in %.1fs",
                label, attempt + 1, err, delay,
            )
            time.sleep(delay)
            attempt += 1

    def _retry_delay(self, attempt: int, retry_after: Optional[float]) -> float:
        if retry_after is not None:
            return min(retry_after, 30.0)
        return self.backoff_base * (2 ** attempt) + random.uniform(0, self.backoff_base / 2)

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.status_code < 400:
            return
        detail, code = resp.reason, None
        try:
            body = resp.json()
            detail = body.get("detail", detail)
            code = body.get("code")
        except ValueError:
            pass
        err = BackendError(
            f"HTTP {resp.status_code}: {detail}",
            status_code=resp.status_code,
            code=code,
            retryable=resp.status_code in _RETRYABLE_STATUS,
        )
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                err._retry_after = float(ra)
            except ValueError:
                pass
        raise err

    @staticmethod
    def _json(resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except ValueError as e:
            raise BackendError(f"non-JSON response: {resp.text[:200]!r}", resp.status_code) from e
        if not isinstance(data, dict):
            raise BackendError(f"unexpected JSON: {data!r}", resp.status_code)
        return data


def _parse_sse(lines) -> Iterator[Tuple[str, dict]]:
    """Minimal SSE parser: yields (event, json-data) per blank-line-terminated frame."""
    event, data_lines = "message", []
    for line in lines:
        if line is None:
            continue
        if line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = {"raw": raw}
                yield event, payload if isinstance(payload, dict) else {"value": payload}
            event, data_lines = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
