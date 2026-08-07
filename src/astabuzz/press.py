"""Turning a button number into a keystroke, at a humane rate."""

import threading
import time
from collections.abc import Callable
from typing import Final

from astabuzz.buttons import DEFAULT_COUNT, Button, get_button
from astabuzz.keyboard import KeyInjector

# The official tester enforces the same gap between consecutive presses of one
# button (GUARD_MS), and its on-screen notes tell users to wait a moment. This
# matches the hardware's behaviour and stops a remote user machine-gunning a bid.
COOLDOWN_S: Final[float] = 0.8


class CooldownError(Exception):
    def __init__(self, remaining_s: float) -> None:
        self.remaining_s = remaining_s
        super().__init__(f"wait {remaining_s:.2f}s")


class PressService:
    def __init__(
        self,
        injector: KeyInjector,
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_s: float = COOLDOWN_S,
        on_press: Callable[[Button], None] | None = None,
        count: int = DEFAULT_COUNT,
    ) -> None:
        self._injector = injector
        self._clock = clock
        self._cooldown_s = cooldown_s
        self._on_press = on_press
        # One source of truth for how many buttons are in play: the server asks
        # this rather than being told separately and drifting out of step.
        self.count = count
        self._last: dict[int, float] = {}
        # The server is threaded, so two presses can arrive at once. The lock
        # covers the tap as well as the check: interleaving the key-down of one
        # letter with the key-up of another would deliver the wrong input.
        self._lock = threading.Lock()

    def press(self, number: object) -> Button:
        """Press a button, or explain why not.

        Raises:
            ValueError: The number is not one of the eight buttons.
            CooldownError: That button was pressed too recently.
        """
        button = get_button(number, self.count)
        assert isinstance(number, int)  # noqa: S101 - narrowed by get_button

        with self._lock:
            now = self._clock()
            last = self._last.get(number)
            if last is not None and (elapsed := now - last) < self._cooldown_s:
                raise CooldownError(self._cooldown_s - elapsed)
            self._injector.tap(button.letter)
            # Recorded after a successful tap, so a failed injection does not
            # burn the user's cooldown.
            self._last[number] = now

        if self._on_press is not None:
            self._on_press(button)
        return button
