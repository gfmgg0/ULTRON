"""Prefer reachable IPv4 routes for Google and OpenAI APIs; retain IPv6 fallback."""
import socket


def prefer_api_ipv4():
    previous = socket.getaddrinfo
    if getattr(previous, "_ultron_api_ipv4", False):
        return

    def resolve(host, *args, **kwargs):
        addresses = previous(host, *args, **kwargs)
        addresses.sort(key=lambda address: address[0] != socket.AF_INET)
        return addresses

    resolve._ultron_api_ipv4 = True
    socket.getaddrinfo = resolve
