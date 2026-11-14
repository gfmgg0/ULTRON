"""Prefer reachable IPv4 routes and cache DNS lookups to prevent transient resolver hiccups."""
import socket
import time

_DNS_CACHE: dict[tuple, tuple[float, list]] = {}
_DNS_TTL = 300.0


def prefer_api_ipv4():
    previous = socket.getaddrinfo
    if getattr(previous, "_ultron_api_ipv4", False):
        return

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        key = (host, port, family, type, proto, flags)
        now = time.monotonic()
        cached = _DNS_CACHE.get(key)
        if cached and (now - cached[0]) < _DNS_TTL:
            return list(cached[1])

        last_exc = None
        for _ in range(3):
            try:
                addresses = previous(host, port, family, type, proto, flags)
                addresses.sort(key=lambda address: address[0] != socket.AF_INET)
                _DNS_CACHE[key] = (now, addresses)
                return list(addresses)
            except socket.gaierror as exc:
                last_exc = exc
                if cached:
                    return list(cached[1])
                time.sleep(0.15)
        raise last_exc  # type: ignore[misc]

    resolve._ultron_api_ipv4 = True
    socket.getaddrinfo = resolve
