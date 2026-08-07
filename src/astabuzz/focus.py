"""Which application a keystroke is about to reach.

Diagnostics only. Nothing here steers the keystroke: a press is a plain key
event and goes wherever macOS routes it, exactly like the physical buzzer,
which is itself just a USB keyboard. Knowing the receiving app is still worth
logging, because "the letter arrived but the wrong window had focus" is
otherwise invisible.

NSWorkspace.frontmostApplication() is deliberately not used: it caches its
value and only refreshes when a run loop pumps notifications, so inside a
long-lived server it reports an app that stopped being frontmost minutes ago.
The window server is asked directly instead, which is always live.
"""


def frontmost_app() -> str:
    """Name of the application that will receive a keystroke right now."""
    try:
        from Quartz import (  # noqa: PLC0415
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )

        windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )
        for window in windows or ():
            # Layer 0 is the normal window layer; menus and overlays sit above it.
            if window.get("kCGWindowLayer") == 0:
                return str(window.get("kCGWindowOwnerName") or "?")
    except Exception:  # noqa: BLE001 - diagnostics must never break a press
        return "?"
    return "?"
