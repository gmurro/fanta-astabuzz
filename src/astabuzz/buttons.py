"""The button-to-letter table.

Transcribed from the inline JavaScript of the official tester at
https://www.fantabuzzer.com/kit-tester.html. The buttons enumerate as a USB
keyboard (vendorId 0x05AC, productId 0x020B) and each one types a single
letter; the tester's WebHID code only reports presence, and detects presses
with a plain keydown listener.

Twelve buttons, P1 to P12, typing A to L. How many are actually offered is
chosen at startup and defaults to eight, the size of the kit in this lega; a
button beyond that count can never be pressed, by anyone, for any reason.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Button:
    label: str
    letter: str


BUTTONS: Final[tuple[Button, ...]] = (
    Button("P1", "A"),
    Button("P2", "B"),
    Button("P3", "C"),
    Button("P4", "D"),
    Button("P5", "E"),
    Button("P6", "F"),
    Button("P7", "G"),
    Button("P8", "H"),
    Button("P9", "I"),
    Button("P10", "J"),
    Button("P11", "K"),
    Button("P12", "L"),
)

DEFAULT_COUNT: Final[int] = 8
MAX_COUNT: Final[int] = len(BUTTONS)


def get_button(number: object, count: int = DEFAULT_COUNT) -> Button:
    """Return the button at 1-based position `number`.

    Args:
        number: Position, 1 through `count`. Typed as `object` because it
            arrives from JSON and has not been validated yet.
        count: How many buttons are in play for this auction.

    Returns:
        The matching `Button`.

    Raises:
        ValueError: If `number` is not an int, or is outside 1..count.
    """
    # bool is a subclass of int, so JSON `true` would otherwise index P1.
    if isinstance(number, bool) or not isinstance(number, int):
        msg = f"button must be an integer, got {type(number).__name__}"
        # ValueError rather than the TypeError ruff would prefer: this value
        # comes off the wire, so a wrong type is bad input rather than a bug,
        # and callers get one exception to catch for every rejected button.
        raise ValueError(msg)  # noqa: TRY004
    if not 1 <= number <= count:
        msg = f"button {number} out of range, expected 1..{count}"
        raise ValueError(msg)
    return BUTTONS[number - 1]
