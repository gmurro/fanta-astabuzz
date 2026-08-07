import ipaddress

from astabuzz.net import ALL_INTERFACES, LOOPBACK, lan_ip


def test_lan_ip_is_a_real_address_other_devices_could_use():
    address = lan_ip()
    if address is None:
        return  # offline; nothing to assert
    parsed = ipaddress.IPv4Address(address)
    # A phone on the wifi cannot reach 127.0.0.1, which is the whole point.
    assert not parsed.is_loopback


def test_constants():
    assert LOOPBACK == "127.0.0.1"
    assert ALL_INTERFACES == "0.0.0.0"  # noqa: S104
