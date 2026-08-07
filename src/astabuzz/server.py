"""The loopback HTTP service the tunnel points at.

Four routes, no framework. The whole security argument for this project is that
there is almost nothing here: no filesystem access, no subprocess, no template
engine, and a request body that cannot exceed a kilobyte. The only side effect
reachable from the network is tapping one of eight whitelisted letters.
"""

import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final

from astabuzz import __version__
from astabuzz.buttons import BUTTONS, MAX_COUNT
from astabuzz.net import LOOPBACK
from astabuzz.press import CooldownError, PressService

MAX_BODY: Final[int] = 1024
WRONG_PIN_DELAY_S: Final[float] = 0.25
COOKIE_NAME: Final[str] = "fb_session"
WEB: Final[Path] = Path(__file__).parent / "web"
INDEX: Final[Path] = WEB / "index.html"
# An exact-match table rather than a path join: there is no user-supplied path
# anywhere in the lookup, so directory traversal is impossible by construction.
STATIC: Final[dict[str, tuple[Path, str]]] = {
    "/logo.webp": (WEB / "logo.webp", "image/webp"),
    "/icon.png": (WEB / "icon.png", "image/png"),
    # Two sizes: the grid shows eight at thumbnail size, the buzz screen one
    # large. Serving the large one eight times was the slow first paint.
    **{
        f"/button-{n}{suffix}.webp": (WEB / f"button-{n}{suffix}.webp", "image/webp")
        for n in range(1, MAX_COUNT + 1)
        for suffix in ("", "-sm")
    },
}


class Sessions:
    def __init__(self) -> None:
        self._tokens: set[str] = set()
        self._lock = threading.Lock()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens.add(token)
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            return token in self._tokens


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fb"
    sys_version = ""

    # Injected by make_server via a subclass.
    pin: str
    sessions: Sessions
    press_service: PressService
    secure_cookies: bool
    on_event: Callable[[str], None] | None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002
        # The press log is the operator's signal; per-request noise would bury it.
        return

    def _event(self, message: str) -> None:
        """Surface a rejected request to the operator.

        A phone showing an error is useless on its own: only the person at the
        Mac can see why the request was turned away.
        """
        if self.on_event is not None:
            self.on_event(f"{self.client_address[0]}  {message}")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_page()
        elif path in STATIC:
            asset, mimetype = STATIC[path]
            self._send_file(asset, mimetype, cache="public, max-age=86400")
        elif path == "/api/config":
            if not self._authed():
                return
            count = self.press_service.count
            buttons = [
                {"n": n, "label": b.label}
                for n, b in enumerate(BUTTONS[:count], start=1)
            ]
            self._json(HTTPStatus.OK, {"buttons": buttons})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        # SameSite=Strict already blocks cross-site cookies; requiring a header
        # a cross-origin form cannot set without a preflight closes the gap.
        if self.headers.get("X-FB") != "1":
            self._event(f"{path}: header X-FB mancante (user-agent o proxy?)")
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        body = self._read_json()
        if body is None:
            length = self.headers.get("Content-Length")
            self._event(f"{path}: corpo non leggibile (Content-Length={length})")
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        if path == "/api/login":
            self._login(body)
        elif path == "/api/press":
            self._press(body)
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _login(self, body: dict[str, Any]) -> None:
        supplied = body.get("pin")
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, self.pin):
            # The received value is shown so a genuinely-correct PIN being
            # refused is diagnosable instead of a mystery. It is the operator's
            # own screen, and the PIN dies with the session.
            self._event(f"PIN rifiutato: ricevuto {supplied!r}, atteso {self.pin!r}")
            # Not a lockout: nothing is remembered and nobody is ever blocked.
            # It only makes exhausting 10,000 PINs take ~40 minutes, not ~20s.
            time.sleep(WRONG_PIN_DELAY_S)
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "bad_pin"})
            return
        token = self.sessions.create()
        attrs = f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/"
        if self.secure_cookies:
            attrs += "; Secure"
        self._json(HTTPStatus.OK, {"ok": True}, cookie=attrs)

    def _press(self, body: dict[str, Any]) -> None:
        if not self._authed():
            return
        try:
            button = self.press_service.press(body.get("button"))
        except CooldownError as exc:
            self._json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {
                    "error": "cooldown",
                    "retry_after_ms": max(1, round(exc.remaining_s * 1000)),
                },
            )
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_button"})
        else:
            self._json(HTTPStatus.OK, {"ok": True, "label": button.label})

    def _authed(self) -> bool:
        if self.sessions.valid(self._token()):
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"error": "auth"})
        return False

    def _token(self) -> str | None:
        for chunk in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = chunk.strip().partition("=")
            if name == COOKIE_NAME:
                return value
        return None

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if not 0 < length <= MAX_BODY:
            return None
        try:
            parsed = json.loads(self.rfile.read(length))
        except json.JSONDecodeError, UnicodeDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _send_page(self) -> None:
        """Serve the page with asset URLs stamped by version.

        Assets are cached hard, so without the stamp a client that saw an older
        release keeps its copy of /logo.webp for a day -- which is how the old
        wordmark survived a rebrand.
        """
        payload = INDEX.read_text().replace("{{v}}", __version__).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path, mimetype: str, cache: str = "no-store") -> None:
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def _json(
        self, status: HTTPStatus, body: dict[str, Any], *, cookie: str | None = None
    ) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)


def make_server(  # noqa: PLR0913 - all six are genuinely independent knobs
    press_service: PressService,
    pin: str,
    *,
    port: int = 0,
    host: str = LOOPBACK,
    secure_cookies: bool = False,
    on_event: Callable[[str], None] | None = None,
) -> ThreadingHTTPServer:
    """Build the server.

    `host` defaults to loopback; callers pass ALL_INTERFACES to let phones on
    the same wifi reach it.
    """
    handler = type(
        "BoundHandler",
        (_Handler,),
        {
            "pin": pin,
            "sessions": Sessions(),
            "press_service": press_service,
            "secure_cookies": secure_cookies,
            # staticmethod, or Python binds the plain function as a method and
            # calls it with the handler as an extra first argument.
            "on_event": staticmethod(on_event) if on_event is not None else None,
        },
    )
    return ThreadingHTTPServer((host, port), handler)
