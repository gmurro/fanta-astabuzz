import re

from astabuzz.cli import generate_pin


def test_generate_pin_is_four_digits():
    for _ in range(50):
        assert re.fullmatch(r"\d{4}", generate_pin())


def test_generate_pin_varies():
    # Not a randomness test, just a guard against a hardcoded constant.
    assert len({generate_pin() for _ in range(60)}) > 1
