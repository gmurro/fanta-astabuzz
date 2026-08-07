import pytest

from astabuzz.buttons import BUTTONS
from astabuzz.keyboard import KEYCODES, FakeKeyInjector, MacKeyInjector


def test_every_button_letter_has_a_keycode():
    for button in BUTTONS:
        assert button.letter in KEYCODES


def test_keycode_table_covers_exactly_the_buttons_in_use():
    # An entry for a letter no button types would be a whitelist hole.
    assert set(KEYCODES) == {b.letter for b in BUTTONS}


def test_keycodes_are_the_ansi_virtual_keycodes():
    # kVK_ANSI_* from Carbon HIToolbox Events.h. These are positional, which is
    # what makes the synthesized event equivalent to the hardware one.
    assert KEYCODES == {
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


def test_fake_injector_records_taps():
    injector = FakeKeyInjector()
    injector.tap("A")
    injector.tap("H")
    assert injector.taps == ["A", "H"]


@pytest.mark.parametrize("letter", ["Z", "a", "", "AB", "1"])
def test_fake_injector_rejects_letters_off_the_whitelist(letter):
    with pytest.raises(ValueError, match="whitelist"):
        FakeKeyInjector().tap(letter)


@pytest.mark.parametrize("letter", ["Z", "a", "", "AB", "1"])
def test_mac_injector_rejects_letters_before_touching_the_os(letter):
    # The whitelist check runs before the Quartz import on purpose, so a bad
    # letter can never reach the OS and this test needs no permissions.
    with pytest.raises(ValueError, match="whitelist"):
        MacKeyInjector().tap(letter)
