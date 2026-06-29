"""Free-port discovery and liveness checks.

IMPORTANT (Windows): a successful ``bind()`` to ``127.0.0.1:<port>`` does NOT mean
the port is free - a server bound to ``0.0.0.0:<port>`` does not block a later
loopback bind unless it set SO_EXCLUSIVEADDRUSE. So we must decide "free" from
what is actually *listening* (across every interface/family, via psutil), not
from whether we can bind.
"""
from __future__ import annotations

import socket

import psutil

HOST = "127.0.0.1"


def listening_ports() -> set[int]:
    """Every TCP port currently in LISTEN state, on any interface/family."""
    ports: set[int] = set()
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr:
                ports.add(c.laddr.port)
    except psutil.Error:
        pass
    return ports


def is_port_listening(port: int, host: str = HOST) -> bool:
    """True if something accepts a connection on the port (server is up)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def _can_bind(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def is_port_free(port: int, host: str = HOST,
                 listening: set[int] | None = None) -> bool:
    """Free only if nothing is listening on it AND we can still bind it."""
    if listening is None:
        listening = listening_ports()
    if port in listening:
        return False
    if is_port_listening(port, host):
        return False
    return _can_bind(port, host)


def find_free_port(start: int, host: str = HOST, limit: int = 65535) -> int:
    """First genuinely-free port at or above ``start``."""
    listening = listening_ports()           # one snapshot of all listeners
    port = max(1, start)
    while port <= limit:
        if (port not in listening
                and not is_port_listening(port, host)
                and _can_bind(port, host)):
            return port
        port += 1
    raise RuntimeError(f"No free port available from {start}")
