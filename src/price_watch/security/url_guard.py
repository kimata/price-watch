#!/usr/bin/env python3
"""URL safety checks for outbound requests."""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse


class UnsafeUrlError(ValueError):
    """Raised when a URL is not allowed for outbound access."""


def _resolve_host_ips(hostname: str) -> set[str]:
    """Resolve hostname to a set of IP addresses."""
    ips: set[str] = set()
    for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
        if family in (socket.AF_INET, socket.AF_INET6):
            host = sockaddr[0]
            if isinstance(host, str):
                ips.add(host)
    return ips


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return addr.is_global


def validate_public_url(url: str, *, allow_schemes: tuple[str, ...] = ("http", "https")) -> None:
    """Validate that a URL is public and safe to access.

    Raises UnsafeUrlError if the URL is not allowed.
    """
    if not url:
        raise UnsafeUrlError("URL is empty")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in allow_schemes:
        raise UnsafeUrlError(f"Disallowed URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise UnsafeUrlError("URL hostname is missing")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL userinfo is not allowed")

    ips = _resolve_host_ips(parsed.hostname)
    if not ips:
        raise UnsafeUrlError("Failed to resolve hostname")

    for ip in ips:
        if not _is_public_ip(ip):
            raise UnsafeUrlError(f"Non-public IP resolved: {ip}")
