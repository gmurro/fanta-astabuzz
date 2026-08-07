"""Finding the address other devices can actually reach.

127.0.0.1 is useless to anyone but this Mac, so the phone in someone's hand
needs the LAN address instead.
"""

import socket

LOOPBACK = "127.0.0.1"
ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - binding the LAN is the point here


def lan_ip() -> str | None:
    """This machine's address on the local network, or None if offline.

    Opens a UDP socket towards a public address and reads back which local
    interface the routing table picked. UDP connect sends no packets, so this
    touches the network stack only, never the network.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        address = str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        sock.close()
    return None if address.startswith("127.") else address
