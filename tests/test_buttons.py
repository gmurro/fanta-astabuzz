import pytest

from astabuzz.buttons import BUTTONS, get_button


def test_the_table_matches_the_official_tester():
    # Transcribed from the official tester at fantabuzzer.com, truncated to
    # the eight buttons in use.
    assert [(b.label, b.letter) for b in BUTTONS] == [
        ("P1", "A"),
        ("P2", "B"),
        ("P3", "C"),
        ("P4", "D"),
        ("P5", "E"),
        ("P6", "F"),
        ("P7", "G"),
        ("P8", "H"),
        ("P9", "I"),
        ("P10", "J"),
        ("P11", "K"),
        ("P12", "L"),
    ]


def test_get_button_returns_the_button_at_a_one_based_position():
    assert get_button(1).letter == "A"
    assert get_button(8).letter == "H"
    assert get_button(8).label == "P8"


@pytest.mark.parametrize("number", [0, 9, -1, 100])
def test_get_button_rejects_numbers_past_the_configured_count(number):
    # Nine is out of range at the default of eight, even though the table holds
    # twelve: only the buttons the lega actually has may be pressed.
    with pytest.raises(ValueError, match="out of range"):
        get_button(number)


def test_a_larger_lega_can_reach_the_higher_buttons():
    assert get_button(12, count=12).letter == "L"
    assert get_button(9, count=12).label == "P9"
    with pytest.raises(ValueError, match="out of range"):
        get_button(13, count=12)


@pytest.mark.parametrize("number", ["8", 8.0, None, [8]])
def test_get_button_rejects_non_integers(number):
    with pytest.raises(ValueError, match="must be an integer"):
        get_button(number)


def test_get_button_rejects_booleans():
    # JSON `true` deserialises to True, and Python treats True == 1, so without
    # an explicit check a boolean would silently press P1.
    with pytest.raises(ValueError, match="must be an integer"):
        get_button(True)  # noqa: FBT003 - passing a boolean is the point here
