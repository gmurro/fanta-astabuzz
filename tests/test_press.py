import pytest

from astabuzz.keyboard import FakeKeyInjector
from astabuzz.press import CooldownError, PressService


class FakeClock:
    # Starts at zero so the boundary cases land on exact floats. Advancing from
    # 1000.0 by 0.8 yields 1000.7999999999999, which would make the
    # "cooldown just expired" tests fail on representation error rather than on
    # behaviour. A monotonic clock is free to start wherever it likes.
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def setup():
    injector = FakeKeyInjector()
    clock = FakeClock()
    return PressService(injector, clock=clock), injector, clock


def test_press_taps_the_letter_for_that_button(setup):
    service, injector, _ = setup
    button = service.press(8)
    assert button.label == "P8"
    assert injector.taps == ["H"]


def test_a_second_press_inside_the_cooldown_is_refused(setup):
    service, injector, clock = setup
    service.press(3)
    clock.advance(0.5)
    with pytest.raises(CooldownError) as excinfo:
        service.press(3)
    assert injector.taps == ["C"]
    assert excinfo.value.remaining_s == pytest.approx(0.3)


def test_the_same_button_works_again_once_the_cooldown_expires(setup):
    service, injector, clock = setup
    service.press(3)
    clock.advance(0.8)
    service.press(3)
    assert injector.taps == ["C", "C"]


def test_the_cooldown_is_per_button(setup):
    service, injector, _ = setup
    service.press(8)
    service.press(3)
    assert injector.taps == ["H", "C"]


@pytest.mark.parametrize("number", [0, 9, -1, "8", 8.0, True, None])
def test_an_invalid_button_taps_nothing(setup, number):
    service, injector, _ = setup
    with pytest.raises(ValueError):  # noqa: PT011
        service.press(number)
    assert injector.taps == []


def test_a_refused_press_does_not_extend_the_cooldown(setup):
    # The failed attempt must not reset the timer, or a user tapping
    # impatiently would lock themselves out indefinitely.
    service, injector, clock = setup
    service.press(1)
    clock.advance(0.5)
    with pytest.raises(CooldownError):
        service.press(1)
    clock.advance(0.3)
    service.press(1)
    assert injector.taps == ["A", "A"]


def test_on_press_receives_the_button():
    injector = FakeKeyInjector()
    seen = []
    service = PressService(injector, clock=FakeClock(), on_press=seen.append)
    service.press(2)
    assert [b.label for b in seen] == ["P2"]


def test_on_press_is_not_called_when_the_press_is_refused():
    injector = FakeKeyInjector()
    clock = FakeClock()
    seen = []
    service = PressService(injector, clock=clock, on_press=seen.append)
    service.press(2)
    with pytest.raises(CooldownError):
        service.press(2)
    assert len(seen) == 1
