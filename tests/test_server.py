import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from astabuzz.keyboard import FakeKeyInjector
from astabuzz.press import PressService
from astabuzz.server import make_server

PIN = "4271"


class Client:
    """Minimal cookie-keeping HTTP client for the test server."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.cookie: str | None = None

    def request(self, method, path, body=None, *, header=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method)  # noqa: S310
        if header:
            req.add_header("X-FB", "1")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                raw = resp.headers.get("Set-Cookie")
                if raw:
                    self.cookie = raw.split(";")[0]
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            return exc.code, json.loads(payload) if payload else None

    def login(self, pin=PIN):
        return self.request("POST", "/api/login", {"pin": pin})

    def press(self, button):
        return self.request("POST", "/api/press", {"button": button})


def _serve(service) -> tuple[ThreadingHTTPServer, threading.Thread, Client]:
    httpd = make_server(service, PIN, port=0, secure_cookies=False)
    # shutdown() waits for serve_forever to notice, so the default 0.5s poll
    # interval would add half a second to every teardown.
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    client = Client(f"http://127.0.0.1:{httpd.server_address[1]}")
    return httpd, thread, client


@pytest.fixture
def server():
    injector = FakeKeyInjector()
    # A cooldown of zero keeps these tests about HTTP; the cooldown itself is
    # covered in test_press.py, and one dedicated case below.
    httpd, thread, client = _serve(PressService(injector, cooldown_s=0))
    yield client, injector
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_the_page_is_served_at_the_root(server):
    client, _ = server
    with urllib.request.urlopen(f"{client.base}/") as resp:  # noqa: S310
        assert resp.status == 200
        assert b"astabuzz" in resp.read()


def test_the_right_pin_opens_a_session(server):
    client, _ = server
    status, body = client.login()
    assert status == 200
    assert body == {"ok": True}
    assert client.cookie is not None


def test_the_wrong_pin_is_refused_and_opens_no_session(server):
    client, _ = server
    status, _ = client.login("0000")
    assert status == 401
    assert client.cookie is None


def test_pressing_without_a_session_is_refused_and_taps_nothing(server):
    client, injector = server
    status, _ = client.press(8)
    assert status == 401
    assert injector.taps == []


def test_pressing_with_a_session_taps_the_letter(server):
    client, injector = server
    client.login()
    status, body = client.press(8)
    assert status == 200
    assert body == {"ok": True, "label": "P8"}
    assert injector.taps == ["H"]


@pytest.mark.parametrize("button", [0, 9, -1, "8", 8.0, True, None])
def test_an_invalid_button_is_refused_and_taps_nothing(server, button):
    client, injector = server
    client.login()
    status, body = client.press(button)
    assert status == 400
    assert body["error"] == "bad_button"
    assert injector.taps == []


def test_a_press_inside_the_cooldown_returns_429_with_the_wait():
    injector = FakeKeyInjector()
    httpd, thread, client = _serve(PressService(injector))
    try:
        client.login()
        assert client.press(5)[0] == 200
        status, body = client.press(5)
        assert status == 429
        assert body["error"] == "cooldown"
        assert 0 < body["retry_after_ms"] <= 800
        assert injector.taps == ["E"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_the_config_lists_the_eight_buttons(server):
    client, _ = server
    client.login()
    status, body = client.request("GET", "/api/config")
    assert status == 200
    assert body["buttons"] == [{"n": n, "label": f"P{n}"} for n in range(1, 9)]


def test_the_config_needs_a_session(server):
    client, _ = server
    assert client.request("GET", "/api/config")[0] == 401


def test_a_post_without_the_x_fb_header_is_refused(server):
    # SameSite=Strict plus a custom header a cross-origin form cannot set.
    client, injector = server
    client.login()
    status, _ = client.request("POST", "/api/press", {"button": 1}, header=False)
    assert status == 400
    assert injector.taps == []


def test_an_oversized_body_is_refused(server):
    client, injector = server
    client.login()
    status, _ = client.request("POST", "/api/press", {"button": 1, "pad": "x" * 2000})
    assert status == 400
    assert injector.taps == []


def test_malformed_json_is_refused(server):
    client, _ = server
    req = urllib.request.Request(  # noqa: S310
        f"{client.base}/api/login", data=b"{not json", method="POST"
    )
    req.add_header("X-FB", "1")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req)  # noqa: S310
    assert excinfo.value.code == 400


def test_an_unknown_path_is_a_404(server):
    client, _ = server
    assert client.request("GET", "/nope")[0] == 404


def test_the_session_cookie_is_hardened(server):
    client, _ = server
    req = urllib.request.Request(  # noqa: S310
        f"{client.base}/api/login",
        data=json.dumps({"pin": PIN}).encode(),
        method="POST",
    )
    req.add_header("X-FB", "1")
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        cookie = resp.headers.get("Set-Cookie")
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Path=/" in cookie


def test_a_wrong_pin_and_a_malformed_request_are_different_statuses():
    # The page shows a different message for each, so conflating them would
    # send the user hunting for the wrong problem.
    injector = FakeKeyInjector()
    httpd, thread, client = _serve(PressService(injector, cooldown_s=0))
    try:
        assert client.login("0000")[0] == 401
        assert (
            client.request("POST", "/api/login", {"pin": PIN}, header=False)[0] == 400
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_rejections_are_reported_to_the_operator():
    seen: list[str] = []

    # A plain function, deliberately: a bound method like `seen.append` would
    # hide the descriptor binding that turns a class-attribute callable into a
    # method and passes the handler as a surprise first argument.
    def record(message: str) -> None:
        seen.append(message)

    httpd = make_server(PressService(FakeKeyInjector()), PIN, port=0, on_event=record)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        Client(f"http://127.0.0.1:{httpd.server_address[1]}").login("0000")
        assert len(seen) == 1
        assert "PIN rifiutato" in seen[0]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_the_config_lists_only_the_buttons_the_lega_has():
    injector = FakeKeyInjector()
    httpd, thread, client = _serve(PressService(injector, cooldown_s=0, count=12))
    try:
        client.login()
        body = client.request("GET", "/api/config")[1]
        assert [b["label"] for b in body["buttons"]][-1] == "P12"
        assert len(body["buttons"]) == 12
        assert client.press(12)[0] == 200
        assert injector.taps == ["L"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_buttons_past_the_configured_count_are_refused():
    injector = FakeKeyInjector()
    httpd, thread, client = _serve(PressService(injector, cooldown_s=0))
    try:
        client.login()
        assert len(client.request("GET", "/api/config")[1]["buttons"]) == 8
        assert client.press(9)[0] == 400
        assert injector.taps == []
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
