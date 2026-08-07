"""Running cloudflared and getting the public URL out of it.

Either kind of tunnel is an outbound connection from this Mac to Cloudflare's
edge. Nothing listens on a routable interface and no inbound port is opened, so
the machine's exposure does not change; the tunnel relays into the local server
for as long as the process lives.

Two kinds:

* **Quick** -- no account, no setup, a random `*.trycloudflare.com` hostname
  that dies with the process. The default.
* **Named** -- a tunnel registered in your own Cloudflare account with a CNAME
  in your zone, so the link is always `astabuzz.example.com`. Needs a one-time
  `cloudflared tunnel login`; after that this module creates the tunnel and the
  DNS record on demand.
"""

import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Final

# Anchored on both sides: the host must end at trycloudflare.com, so a URL
# merely containing that string somewhere cannot be mistaken for the tunnel.
_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com(?![a-z0-9.-])"
)

STOP_TIMEOUT_S: Final[float] = 5.0
CERT = Path.home() / ".cloudflared" / "cert.pem"
READY_TIMEOUT_S: Final[float] = 40.0
_READY_POLL_S: Final[float] = 1.0


def probe(url: str, timeout_s: float = 8.0) -> int:
    """HTTP status of a GET, or 0 if the request could not be completed."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except OSError:
        return 0


def wait_until_ready(
    url: str,
    timeout_s: float = READY_TIMEOUT_S,
    probe_fn: Callable[[str], int] = probe,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bool:
    """Poll until Cloudflare actually routes the URL to us.

    cloudflared prints the hostname as soon as it is allocated, but the edge
    needs a few more seconds before it will serve it; until then requests come
    back as 530 (error 1033). Handing that URL to someone in the meantime means
    they see a failure and blame whatever the page told them -- so the link is
    only announced once it really works.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if probe_fn(url) == 200:  # noqa: PLR2004
            return True
        sleep_fn(_READY_POLL_S)
    return False


class TunnelError(RuntimeError):
    pass


def find_cloudflared() -> str | None:
    return shutil.which("cloudflared")


def extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def tunnel_name_for(hostname: str) -> str:
    """A stable, dashboard-legible tunnel name derived from the hostname.

    Deterministic so that restarting reuses the same tunnel and DNS record
    instead of littering the account with one tunnel per run.
    """
    return "astabuzz-" + hostname.replace(".", "-")


def ensure_named_tunnel(
    hostname: str, run: Callable[..., object] = subprocess.run
) -> str:
    """Make sure a tunnel and its DNS record exist for `hostname`.

    Returns the tunnel name to run. Raises TunnelError with something the
    operator can act on.
    """
    binary = find_cloudflared()
    if binary is None:
        msg = "cloudflared not found on PATH"
        raise TunnelError(msg)
    if not CERT.exists():
        msg = (
            f"not logged in to Cloudflare ({CERT} is missing).\n"
            "  Run this once, it opens a browser:  cloudflared tunnel login"
        )
        raise TunnelError(msg)

    name = tunnel_name_for(hostname)
    listed = run(
        [binary, "tunnel", "list", "-o", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        existing = {t["name"] for t in json.loads(listed.stdout or "[]")}
    except json.JSONDecodeError, TypeError, KeyError:
        existing = set()

    if name not in existing:
        created = run(
            [binary, "tunnel", "create", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            msg = f"could not create tunnel {name}:\n{created.stderr.strip()}"
            raise TunnelError(msg)

    # Deliberately without --overwrite-dns: if that name already points at
    # something else in the zone, say so rather than silently taking it over.
    routed = run(
        [binary, "tunnel", "route", "dns", name, hostname],
        capture_output=True,
        text=True,
        check=False,
    )
    if routed.returncode != 0 and "already exists" not in (routed.stderr or ""):
        msg = f"could not point {hostname} at the tunnel:\n{routed.stderr.strip()}"
        raise TunnelError(msg)
    return name


class Tunnel:
    def __init__(
        self,
        port: int,
        on_log: Callable[[str], None] | None = None,
        hostname: str | None = None,
    ) -> None:
        self._port = port
        self._on_log = on_log
        self._hostname = hostname
        self._process: subprocess.Popen[str] | None = None
        self._url: str | None = None
        self._found = threading.Event()
        self._tail: list[str] = []

    @property
    def url(self) -> str | None:
        return self._url

    def command(self, binary: str) -> list[str]:
        base = [
            binary,
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{self._port}",
        ]
        if self._hostname is None:
            return base
        # --url is a flag on `tunnel`, so it has to precede the run subcommand.
        return [*base, "run", tunnel_name_for(self._hostname)]

    def start(self, timeout_s: float = 30) -> str:
        binary = find_cloudflared()
        if binary is None:
            msg = "cloudflared not found on PATH"
            raise TunnelError(msg)

        if self._hostname is not None:
            # The address is known up front; only the connection is pending.
            self._url = f"https://{self._hostname}"

        self._process = subprocess.Popen(  # noqa: S603
            self.command(binary),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read_output, daemon=True).start()

        if not self._found.wait(timeout_s):
            output = "".join(self._tail[-20:])
            self.stop()
            msg = f"cloudflared gave no URL within {timeout_s:.0f}s:\n{output}"
            raise TunnelError(msg)
        assert self._url is not None  # noqa: S101 - guaranteed by the event
        return self._url

    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=STOP_TIMEOUT_S)

    def _read_output(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self._tail.append(line)
            del self._tail[:-40]
            if self._on_log is not None:
                self._on_log(line.rstrip())
            if self._hostname is not None:
                if "Registered tunnel connection" in line:
                    self._found.set()
            elif self._url is None and (found := extract_url(line)):
                self._url = found
                self._found.set()
