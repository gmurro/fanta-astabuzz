import pytest
from pydantic import ValidationError

from astabuzz.config import Settings


def _settings(tmp_path, body: str) -> Settings:
    env = tmp_path / ".env"
    env.write_text(body)
    return Settings(_env_file=env)


def test_defaults_when_there_is_no_env_file(tmp_path):
    s = _settings(tmp_path, "")
    assert s.pin == ""  # empty means "generate one"
    assert s.domain == ""
    assert s.port == 8787
    assert s.buttons == 8


def test_values_are_read_from_the_env_file(tmp_path):
    s = _settings(
        tmp_path,
        "ASTABUZZ_PIN=1998\nASTABUZZ_DOMAIN=astabuzz.example.com\n"
        "ASTABUZZ_BUTTONS=12\nASTABUZZ_PORT=9000\n",
    )
    assert (s.pin, s.domain, s.buttons, s.port) == (
        "1998",
        "astabuzz.example.com",
        12,
        9000,
    )


@pytest.mark.parametrize("pin", ["123", "12345", "abcd", "19 8"])
def test_a_bad_pin_is_refused_at_startup(tmp_path, pin):
    # Rather than at the first login, when it has already been read out loud.
    with pytest.raises(ValidationError, match="exactly 4 digits"):
        _settings(tmp_path, f"ASTABUZZ_PIN={pin}\n")


@pytest.mark.parametrize(
    "domain", ["https://astabuzz.example.com", "astabuzz", "a b.com"]
)
def test_a_domain_that_is_not_a_hostname_is_refused(tmp_path, domain):
    with pytest.raises(ValidationError, match="bare hostname"):
        _settings(tmp_path, f"ASTABUZZ_DOMAIN={domain}\n")


@pytest.mark.parametrize("count", [0, 13, -1])
def test_button_counts_outside_the_kit_are_refused(tmp_path, count):
    with pytest.raises(ValidationError):
        _settings(tmp_path, f"ASTABUZZ_BUTTONS={count}\n")


def test_the_environment_beats_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTABUZZ_PIN", "4242")
    assert _settings(tmp_path, "ASTABUZZ_PIN=1998\n").pin == "4242"
