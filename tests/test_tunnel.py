import pathlib

import pytest

from astabuzz import tunnel as tunnel_module
from astabuzz.tunnel import (
    Tunnel,
    TunnelError,
    ensure_named_tunnel,
    extract_url,
    tunnel_name_for,
    wait_until_ready,
)

BANNER = """
2026-08-07T18:22:01Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-08-07T18:22:03Z INF +--------------------------------------------------------+
2026-08-07T18:22:03Z INF |  Your quick Tunnel has been created! Visit it at:       |
2026-08-07T18:22:03Z INF |  https://tasty-panda-rides-north.trycloudflare.com      |
2026-08-07T18:22:03Z INF +--------------------------------------------------------+
"""


def test_extracts_the_quick_tunnel_url():
    assert extract_url(BANNER) == "https://tasty-panda-rides-north.trycloudflare.com"


def test_returns_none_before_the_url_appears():
    assert extract_url("INF Requesting new quick Tunnel...") is None


@pytest.mark.parametrize(
    "line",
    [
        "https://evil.com/trycloudflare.com",
        "http://plain-http.trycloudflare.com",
        "https://sub.domain.trycloudflare.com.attacker.net",
    ],
)
def test_ignores_lookalike_urls(line):
    assert extract_url(line) is None


def test_wait_until_ready_returns_once_the_edge_serves_us():
    # cloudflared prints the URL before Cloudflare will route it; the first
    # responses are 530 (error 1033).
    statuses = iter([530, 530, 200])
    slept: list[float] = []
    assert wait_until_ready(
        "https://x.trycloudflare.com",
        timeout_s=30,
        probe_fn=lambda _url: next(statuses),
        sleep_fn=slept.append,
    )
    assert len(slept) == 2


def test_wait_until_ready_gives_up_rather_than_hanging():
    slept: list[float] = []
    assert not wait_until_ready(
        "https://x.trycloudflare.com",
        timeout_s=0,
        probe_fn=lambda _url: 530,
        sleep_fn=slept.append,
    )


def test_the_tunnel_name_is_derived_from_the_hostname():
    # Deterministic, so restarting reuses the tunnel instead of creating a new
    # one on every run.
    assert tunnel_name_for("astabuzz.gmurro.com") == "astabuzz-astabuzz-gmurro-com"


def test_a_quick_tunnel_asks_for_a_throwaway_hostname():
    assert Tunnel(8787).command("cf") == [
        "cf",
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://127.0.0.1:8787",
    ]


def test_a_named_tunnel_runs_the_registered_tunnel():
    # --url is a flag on `tunnel`, so it has to come before the run subcommand.
    assert Tunnel(8787, hostname="astabuzz.gmurro.com").command("cf") == [
        "cf",
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://127.0.0.1:8787",
        "run",
        "astabuzz-astabuzz-gmurro-com",
    ]


def test_setting_up_a_domain_refuses_before_login(monkeypatch):
    # cert.pem is what `cloudflared tunnel login` writes; without it every
    # api call would fail with something far less helpful.
    monkeypatch.setattr(tunnel_module, "CERT", pathlib.Path("/nonexistent/cert.pem"))
    monkeypatch.setattr(
        tunnel_module, "find_cloudflared", lambda: "/usr/bin/cloudflared"
    )
    with pytest.raises(TunnelError, match="cloudflared tunnel login"):
        ensure_named_tunnel("astabuzz.gmurro.com")


def test_setting_up_a_domain_creates_the_tunnel_then_the_record(monkeypatch, tmp_path):
    cert = tmp_path / "cert.pem"
    cert.write_text("x")
    monkeypatch.setattr(tunnel_module, "CERT", cert)
    monkeypatch.setattr(tunnel_module, "find_cloudflared", lambda: "cf")
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(cmd, **_kwargs) -> Result:  # noqa: ANN003
        calls.append(cmd)
        return Result()

    assert ensure_named_tunnel("astabuzz.gmurro.com", run=fake_run) == (
        "astabuzz-astabuzz-gmurro-com"
    )
    assert calls[0][1:3] == ["tunnel", "list"]
    assert calls[1][1:3] == ["tunnel", "create"]
    assert calls[2][1:4] == ["tunnel", "route", "dns"]
    # never --overwrite-dns: an existing record in the zone must not be taken
    assert not any("--overwrite-dns" in c for c in calls)


def test_an_existing_tunnel_is_reused(monkeypatch, tmp_path):
    cert = tmp_path / "cert.pem"
    cert.write_text("x")
    monkeypatch.setattr(tunnel_module, "CERT", cert)
    monkeypatch.setattr(tunnel_module, "find_cloudflared", lambda: "cf")
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = '[{"name": "astabuzz-astabuzz-gmurro-com"}]'
        stderr = ""

    def fake_run(cmd, **_kwargs) -> Result:  # noqa: ANN003
        calls.append(cmd)
        return Result()

    ensure_named_tunnel("astabuzz.gmurro.com", run=fake_run)
    assert not any(c[1:3] == ["tunnel", "create"] for c in calls)
