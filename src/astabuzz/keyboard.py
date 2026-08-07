"""Synthesising the keystroke a physical buzzer would have produced.

A FantaBuzzer button is a USB keyboard that types one letter, so pressing P8
remotely means posting the key event for H. Posting at the HID event tap is the
lowest injection point macOS exposes publicly, so the event travels the same
path as real hardware and lands in whichever application is frontmost.
"""

import time
from typing import Final, Protocol

# kVK_ANSI_* from Carbon HIToolbox Events.h. Virtual keycodes are positional
# and get resolved through the active keyboard layout, exactly as the physical
# button's HID usage codes do. A-L sit in the same place on Italian and US
# QWERTY, so the character produced matches the real button on either layout.
KEYCODES: Final[dict[str, int]] = {
    "A": 0x00,
    "B": 0x0B,
    "C": 0x08,
    "D": 0x02,
    "E": 0x0E,
    "F": 0x03,
    "G": 0x05,
    "H": 0x04,
    "I": 0x22,
    "J": 0x26,
    "K": 0x28,
    "L": 0x25,
}

# How long the key is held down. Long enough that an application polling for
# key state cannot miss it, short enough never to trigger key repeat.
KEY_DOWN_S: Final[float] = 0.012


def _keycode(letter: str) -> int:
    try:
        return KEYCODES[letter]
    except KeyError, TypeError:
        msg = f"letter not on the buzzer whitelist: {letter!r}"
        raise ValueError(msg) from None


class KeyInjector(Protocol):
    def tap(self, letter: str) -> None: ...


class FakeKeyInjector:
    """Records taps instead of posting them, so tests need no permissions."""

    def __init__(self) -> None:
        self.taps: list[str] = []

    def tap(self, letter: str) -> None:
        _keycode(letter)
        self.taps.append(letter)


class MacKeyInjector:
    def tap(self, letter: str) -> None:
        # Validate before importing Quartz: a rejected letter must never reach
        # the OS, and this keeps the failure path testable off-macOS.
        keycode = _keycode(letter)

        from Quartz import (  # noqa: PLC0415
            CGEventCreateKeyboardEvent,
            CGEventPost,
            kCGHIDEventTap,
        )

        down = CGEventCreateKeyboardEvent(None, keycode, True)  # noqa: FBT003
        up = CGEventCreateKeyboardEvent(None, keycode, False)  # noqa: FBT003
        CGEventPost(kCGHIDEventTap, down)
        time.sleep(KEY_DOWN_S)
        CGEventPost(kCGHIDEventTap, up)


def accessibility_granted() -> bool:
    """Whether this process may post key events to other applications."""
    try:
        from ApplicationServices import AXIsProcessTrusted  # noqa: PLC0415
    except ImportError:
        try:
            from HIServices import AXIsProcessTrusted  # noqa: PLC0415
        except ImportError:
            return False
    return bool(AXIsProcessTrusted())
