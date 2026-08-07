"""Command line entry point: preflight, run, and shut everything down together."""

import os
import secrets
import signal
import sys
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import FrameType
from typing import Final

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from astabuzz.buttons import MAX_COUNT, Button
from astabuzz.config import PIN_LENGTH, Settings
from astabuzz.focus import frontmost_app
from astabuzz.keyboard import MacKeyInjector, accessibility_granted
from astabuzz.net import ALL_INTERFACES, lan_ip
from astabuzz.press import PressService
from astabuzz.server import make_server
from astabuzz.tunnel import (
    Tunnel,
    TunnelError,
    ensure_named_tunnel,
    find_cloudflared,
    wait_until_ready,
)

RUN_DIR: Final[Path] = Path.cwd() / ".run"

try:
    settings = Settings()
except ValidationError as exc:
    # A bad .env should read like a typo, not a stack trace.
    problems = "; ".join(
        f"ASTABUZZ_{e['loc'][0].upper()} {e['msg']}" for e in exc.errors()
    )
    console = Console()
    console.print(f"[bold red]x[/] Invalid settings in .env: {problems}")
    raise SystemExit(1) from exc

app = typer.Typer(
    add_completion=False,
    help="Il pulsante dell'asta. Ovunque, da qualsiasi dispositivo.",
)
console = Console()


def generate_pin() -> str:
    return f"{secrets.randbelow(10_000):04d}"


def _fail(message: str, hint: str = "") -> None:
    console.print(f"[bold red]x[/] {message}")
    if hint:
        console.print(f"  [dim]{hint}[/]")
    raise typer.Exit(code=1)


def _preflight(*, use_tunnel: bool) -> None:
    """Fail now, loudly, rather than mid-auction with nine people waiting."""
    if sys.platform != "darwin":
        _fail("This release supports macOS only.")
    if not accessibility_granted():
        _fail(
            "Accessibility permission is not granted, so no keystroke can be sent.",
            "System Settings > Privacy & Security > Accessibility > enable your "
            "terminal app, then restart the terminal and try again.",
        )
    if use_tunnel and find_cloudflared() is None:
        _fail("cloudflared is not installed.", "brew install cloudflared")


RUNTIME_FILES: Final[tuple[str, ...]] = (
    "server.pid",
    "url.txt",
    "pin.txt",
    "port.txt",
)


def _resolve_pin(pin: str) -> str:
    if pin and (len(pin) != PIN_LENGTH or not pin.isdigit()):
        _fail(f"The PIN must be exactly {PIN_LENGTH} digits.")
    return pin or generate_pin()


def _log_reject(message: str) -> None:
    stamp = datetime.now().astimezone().strftime("%H:%M:%S")
    console.print(f"[dim]{stamp}[/]  [bold red]rifiutata[/]  {message}")


def _log_press(button: Button) -> None:
    stamp = datetime.now().astimezone().strftime("%H:%M:%S")
    console.print(
        f"[dim]{stamp}[/]  [bold green]{button.label}[/] "
        f"([bold]{button.letter}[/]) -> {frontmost_app()}"
    )


def _log_tunnel(line: str) -> None:
    """Surface cloudflared's own verdict.

    A quick tunnel occasionally gets a hostname but never registers a
    connection, and then every request comes back as Cloudflare 530. Without
    this line that failure is invisible here and looks, to whoever holds the
    link, like the app being broken.
    """
    if "Registered tunnel connection" in line:
        console.print("[dim]Tunnel registrato.[/]")
    elif "ERR" in line:
        console.print(f"[yellow]![/] cloudflared: {line.strip()}")


def _open_tunnel(
    port: int, httpd: ThreadingHTTPServer, domain: str | None = None
) -> tuple[Tunnel, str]:
    if domain:
        try:
            ensure_named_tunnel(domain)
        except TunnelError as exc:
            httpd.server_close()
            _fail("Could not set up the custom domain.", str(exc))
    tunnel = Tunnel(port, on_log=_log_tunnel, hostname=domain)
    console.print("[dim]Apertura del tunnel...[/]")
    try:
        url = tunnel.start()
    except TunnelError as exc:
        # Close the listener before exiting, or the port stays bound.
        httpd.server_close()
        _fail("The tunnel did not come up.", str(exc))
    return tunnel, url


def _verify_tunnel(url: str) -> None:
    """Confirm the public link really works, without holding up startup."""
    if wait_until_ready(url):
        console.print("[green]v[/] Link pubblico raggiungibile.\n")
    else:
        console.print(
            "[yellow]![/] Il link pubblico non risponde (errore 530 di "
            "Cloudflare: il tunnel non si è registrato).\n"
            "  Usa l'indirizzo di rete locale, oppure ferma e riavvia per "
            "ottenere un tunnel nuovo.\n"
        )


def _write_runtime_files(url: str, pin: str, port: int) -> None:
    """Record state for `make status` and `make stop`.

    The PID is written by the process itself: `uv run` interposes a process, so
    the shell's $! would point at the wrong one.
    """
    RUN_DIR.mkdir(exist_ok=True)
    (RUN_DIR / "server.pid").write_text(f"{os.getpid()}\n")
    (RUN_DIR / "url.txt").write_text(f"{url}\n")
    (RUN_DIR / "pin.txt").write_text(f"{pin}\n")
    # `make stop` reads this rather than assuming a default that .env may have
    # changed underneath it.
    (RUN_DIR / "port.txt").write_text(f"{port}\n")


def _announce(local_url: str, tunnel_url: str | None, pin: str) -> None:
    lines = [f"In casa (stesso wifi)   [bold]{local_url}[/]"]
    if tunnel_url:
        lines.append(f"Da fuori casa           [bold]{tunnel_url}[/]")
    lines.append(f"\nPIN  [bold yellow]{pin}[/]")
    console.print(
        Panel(
            "\n".join(lines),
            title="fanta-astabuzz",
            subtitle="Ctrl-C per fermare tutto",
            border_style="green",
        )
    )
    console.print(
        "[dim]Ogni pressione digita la lettera del pulsante, come il buzzer "
        "fisico: arriva all'app in primo piano.[/]\n"
    )


def _handle_signals(httpd: ThreadingHTTPServer) -> None:
    stopping = threading.Event()

    def shutdown(_signum: int, _frame: FrameType | None) -> None:
        if stopping.is_set():
            return
        stopping.set()
        # shutdown() blocks until serve_forever returns, which cannot happen
        # from inside a handler running on the serving thread.
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)


@app.command()
def start(  # noqa: PLR0913, PLR0917 - each option is an independent switch
    pin: str = typer.Option(
        settings.pin, help="4-digit PIN. Generated at random if omitted."
    ),
    buttons: int = typer.Option(
        settings.buttons,
        min=1,
        max=MAX_COUNT,
        help=f"How many buttons the lega has, 1 to {MAX_COUNT}.",
    ),
    port: int = typer.Option(
        settings.port, help="Port to listen on, on every interface."
    ),
    domain: str = typer.Option(
        settings.domain,
        help="Publish on your own Cloudflare hostname, e.g. astabuzz.example.com. "
        "Needs `cloudflared tunnel login` once. Omit for a throwaway link.",
    ),
    no_tunnel: bool = typer.Option(
        False, "--no-tunnel", help="Local only, no public URL."
    ),
    pgroup: bool = typer.Option(
        False,
        "--pgroup",
        help="Become a process group leader so `make stop` can signal the group. "
        "Used by `make start`; leave off in the foreground or Ctrl-C stops working.",
    ),
) -> None:
    use_tunnel = not no_tunnel
    _preflight(use_tunnel=use_tunnel)
    pin = _resolve_pin(pin)

    if domain and use_tunnel:
        console.print(
            f"[yellow]![/] {domain} è un indirizzo fisso e indovinabile, a "
            "differenza del link usa-e-getta.\n"
            "  Resta raggiungibile solo mentre il server gira, ma con un PIN di "
            "4 cifre valuta un PIN più lungo.\n"
        )

    if pgroup:
        os.setpgrp()

    service = PressService(MacKeyInjector(), on_press=_log_press, count=buttons)
    # Bound on every interface so phones on the same wifi can reach it; the
    # keystroke itself is all this can ever do, whoever sends it.
    httpd = make_server(
        service, pin, port=port, host=ALL_INTERFACES, on_event=_log_reject
    )
    actual_port = httpd.server_address[1]

    # The loopback address is useless to anyone holding a phone.
    host_ip = lan_ip()
    if host_ip is None:
        console.print(
            "[yellow]![/] Nessun indirizzo di rete locale: sei offline? "
            "Raggiungibile solo da questo Mac."
        )
        host_ip = "127.0.0.1"
    local_url = f"http://{host_ip}:{actual_port}"

    tunnel: Tunnel | None = None
    tunnel_url: str | None = None
    if use_tunnel:
        tunnel, tunnel_url = _open_tunnel(actual_port, httpd, domain or None)

    _write_runtime_files(tunnel_url or local_url, pin, actual_port)
    _announce(local_url, tunnel_url, pin)
    if tunnel_url is not None:
        # Checked in the background: the operator gets the links immediately,
        # and a verdict on the public one a few seconds later.
        threading.Thread(target=_verify_tunnel, args=(tunnel_url,), daemon=True).start()
    _handle_signals(httpd)

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        if tunnel is not None:
            tunnel.stop()
        for name in RUNTIME_FILES:
            (RUN_DIR / name).unlink(missing_ok=True)
        console.print("\n[dim]Fermato. Tunnel chiuso.[/]")
