"""Opt-in HTTPS delivery boundary for the R7 status-only content contract.

The caller supplies operator-owned configuration in memory. This module does
not read environment variables, persist endpoints, log them, or discover them
from a task or candidate checkout. Delivery defaults to dry-run and disabled.
"""

import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

from orchestrator.core.status_notification import (
    StatusNotification,
    StatusNotificationError,
    validate_status_notification,
)

_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_PATH = re.compile(r"/[A-Za-z0-9/_-]{0,255}")
_MAX_NOTICE_JSON = 512
_MAX_ENDPOINT = 512
_MAX_HOSTS = 8


class NotificationDeliveryError(RuntimeError):
    """A non-authorizing, endpoint-free delivery failure."""


@dataclass(frozen=True)
class NotificationDeliveryConfig:
    """Ephemeral operator-owned URL, exact host allowlist and public IP pin."""

    endpoint_url: str = field(repr=False)
    allowed_hosts: tuple[str, ...] = field(repr=False)
    endpoint_ip: str = field(repr=False)
    enabled: bool = False
    timeout_seconds: int = 5

    def __post_init__(self) -> None:
        _validated_target(self)


@dataclass(frozen=True)
class NotificationDeliveryResult:
    """Transport outcome only; never evidence of review, approval or delivery."""

    state: str  # DRY_RUN or HTTP_ACCEPTED


def _deny() -> NotificationDeliveryError:
    return NotificationDeliveryError("Notification delivery blocked")


def _valid_host(host: str) -> bool:
    return type(host) is str and len(host) <= 253 and _HOST.fullmatch(host) is not None


def _validated_ip(value: str) -> tuple[str, int]:
    if type(value) is not str:
        raise _deny()
    invalid = False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        invalid = True
    if invalid:
        raise _deny()
    if not address.is_global or str(address) != value:
        raise _deny()
    return value, address.version


def _validated_target(config: NotificationDeliveryConfig) -> tuple[str, str, str]:
    if (type(config.enabled) is not bool or type(config.timeout_seconds) is not int
            or not 1 <= config.timeout_seconds <= 10):
        raise _deny()
    hosts = config.allowed_hosts
    if (type(hosts) is not tuple or not 1 <= len(hosts) <= _MAX_HOSTS
            or any(not _valid_host(host) for host in hosts)
            or len(set(hosts)) != len(hosts)):
        raise _deny()
    url = config.endpoint_url
    if (type(url) is not str or not 1 <= len(url) <= _MAX_ENDPOINT
            or any(not 33 <= ord(char) <= 126 or char in "\\?#" for char in url)):
        raise _deny()
    invalid_url = False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        invalid_url = True
    if invalid_url:
        raise _deny()
    if (parts.scheme != "https" or not _valid_host(host)
            or parts.netloc != host or port is not None
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or host not in hosts):
        raise _deny()
    path = parts.path or "/"
    if (_PATH.fullmatch(path) is None or "//" in path
            or any(segment == ".." for segment in path.split("/"))):
        raise _deny()
    ip, _version = _validated_ip(config.endpoint_ip)
    return host, path, ip


def _validated_notice(notice: StatusNotification) -> StatusNotification:
    if (type(notice) is not StatusNotification or type(notice.payload_json) is not str
            or not 1 <= len(notice.payload_json) <= _MAX_NOTICE_JSON
            or type(notice.text) is not str):
        raise _deny()
    invalid_notice = False
    try:
        rebuilt = validate_status_notification(json.loads(notice.payload_json))
    except (TypeError, ValueError, StatusNotificationError):
        invalid_notice = True
    if invalid_notice:
        raise _deny()
    # Reject forged text, noncanonical JSON and duplicate JSON keys rather than
    # forwarding caller-controlled content, even when the dataclass was forged.
    if rebuilt != notice:
        raise _deny()
    return rebuilt


def _send_https(host: str, path: str, ip: str, body: bytes, timeout_seconds: int) -> int:
    """One TLS-verified HTTPS POST to the configured IP, without DNS or redirects."""
    _ip, version = _validated_ip(ip)
    family = socket.AF_INET if version == 4 else socket.AF_INET6
    raw = socket.socket(family, socket.SOCK_STREAM)
    try:
        raw.settimeout(timeout_seconds)
        raw.connect((ip, 443))
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    except Exception:
        raw.close()
        raise
    connection = http.client.HTTPSConnection(host, timeout=timeout_seconds)
    connection.sock = tls  # Already connected to the pinned IP; no DNS lookup.
    try:
        connection.request(
            "POST", path, body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Connection": "close"},
        )
        response = connection.getresponse()
        return response.status  # No response body is read, logged or returned.
    finally:
        connection.close()


def deliver_status_notification(
    notice: StatusNotification,
    config: NotificationDeliveryConfig,
    *,
    dry_run: bool = True,
    transport: Callable[[str, str, str, bytes, int], int] | None = None,
) -> NotificationDeliveryResult:
    """Validate and optionally POST one fixed-field notice; never retry or redirect.

    ``transport`` is for isolated tests. Runtime callers must provide their own
    trusted, operator-owned configuration; task and PR text are untrusted.
    """
    if type(config) is not NotificationDeliveryConfig or type(dry_run) is not bool:
        raise _deny()
    host, path, ip = _validated_target(config)
    safe_notice = _validated_notice(notice)
    if dry_run:
        return NotificationDeliveryResult("DRY_RUN")
    if not config.enabled:
        raise _deny()
    if transport is not None and not callable(transport):
        raise _deny()
    sender = transport if transport is not None else _send_https
    blocked = False
    uncertain = False
    status: object = None
    try:
        status = sender(host, path, ip, safe_notice.payload_json.encode("ascii"),
                        config.timeout_seconds)
    except NotificationDeliveryError:
        blocked = True
    except Exception:
        uncertain = True
    if blocked:
        raise _deny()
    if uncertain:
        # The request may have reached the server. Do not claim a safe retry.
        raise NotificationDeliveryError("Notification delivery outcome unconfirmed")
    if type(status) is not int or not 200 <= status <= 299:
        raise NotificationDeliveryError("Notification endpoint did not accept the notice")
    return NotificationDeliveryResult("HTTP_ACCEPTED")
