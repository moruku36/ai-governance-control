"""R7 delivery boundary: synthetic configuration and transport only."""

import json

import pytest

from orchestrator.adapters import status_notification as adapter
from orchestrator.adapters.status_notification import (
    NotificationDeliveryConfig,
    NotificationDeliveryError,
    deliver_status_notification,
)
from orchestrator.core.status_notification import (
    StatusNotification,
    build_status_notification,
)

HOST = "hooks.example.test"
URL = f"https://{HOST}/synthetic-hook"
PUBLIC_TEST_IP = "8.8.8.8"  # Shape-only fixture; no connection is made.


def config(**overrides):
    values = {"endpoint_url": URL, "allowed_hosts": (HOST,),
              "endpoint_ip": PUBLIC_TEST_IP, "enabled": False,
              "timeout_seconds": 3}
    values.update(overrides)
    return NotificationDeliveryConfig(**values)


def notice():
    return build_status_notification(
        task_id="SMP-001", repository_id="synthetic-repo",
        event="review_needed", occurred_at="2026-10-23T05:00:00Z",
    )


def test_dry_run_is_default_even_when_enabled_and_never_calls_transport(monkeypatch):
    def forbidden(*_args):
        raise AssertionError("network transport called")

    monkeypatch.setattr(adapter, "_send_https", forbidden)
    assert deliver_status_notification(notice(), config(enabled=True)).state == "DRY_RUN"
    assert deliver_status_notification(notice(), config()).state == "DRY_RUN"


def test_disabled_config_refuses_live_delivery_before_transport():
    calls = []
    with pytest.raises(NotificationDeliveryError, match="blocked"):
        deliver_status_notification(notice(), config(), dry_run=False,
                                    transport=lambda *_args: calls.append(1))
    assert calls == []


def test_explicit_enabled_delivery_sends_only_canonical_status_json_once():
    calls = []

    def fake_transport(host, path, ip, body, timeout):
        calls.append((host, path, ip, body, timeout))
        return 204

    sent = deliver_status_notification(notice(), config(enabled=True), dry_run=False,
                                       transport=fake_transport)
    assert sent.state == "HTTP_ACCEPTED"
    assert len(calls) == 1
    host, path, ip, body, timeout = calls[0]
    assert (host, path, ip, timeout) == (HOST, "/synthetic-hook", PUBLIC_TEST_IP, 3)
    assert body == notice().payload_json.encode("ascii")
    assert set(json.loads(body)) == {
        "contract_version", "task_id", "repository_id", "event", "occurred_at",
    }
    assert set(sent.__dataclass_fields__) == {"state"}


@pytest.mark.parametrize("bad_url", [
    "http://hooks.example.test/synthetic-hook",
    "https://127.0.0.1/synthetic-hook",
    "https://localhost/synthetic-hook",
    "https://hooks.example.test:443/synthetic-hook",
    "https://hooks.example.test:SYNTHETIC/synthetic-hook",
    "https://user@hooks.example.test/synthetic-hook",
    "https://hooks.example.test/synthetic-hook?key=SYNTHETIC",
    "https://hooks.example.test/synthetic-hook#fragment",
    "https://hooks.example.test/%2Fsynthetic-hook",
    "https://hooks.example.test//synthetic-hook",
    "https://hooks.example.test/../synthetic-hook",
    "https://hooks.example.test\\@evil.example.test/synthetic-hook",
    "https://hоoks.example.test/synthetic-hook",  # Cyrillic o
    " https://hooks.example.test/synthetic-hook",
    "https://other.example.test/synthetic-hook",
])
def test_bad_endpoint_is_refused_without_echo(bad_url):
    with pytest.raises(NotificationDeliveryError) as caught:
        config(endpoint_url=bad_url)
    assert bad_url not in str(caught.value)
    assert "SYNTHETIC" not in str(caught.value)


@pytest.mark.parametrize("bad_hosts", [
    (), ("*.example.test",), ("other.example.test",), (HOST, HOST),
    [HOST], (HOST, 7),
])
def test_allowlist_requires_exact_typed_hostnames(bad_hosts):
    with pytest.raises(NotificationDeliveryError):
        config(allowed_hosts=bad_hosts)


@pytest.mark.parametrize("bad_ip", [
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "not-an-ip", 7,
])
def test_ip_pin_must_be_a_canonical_public_address(bad_ip):
    with pytest.raises(NotificationDeliveryError) as caught:
        config(endpoint_ip=bad_ip)
    assert str(bad_ip) not in str(caught.value)


@pytest.mark.parametrize("field,value", [
    ("enabled", 1), ("timeout_seconds", 0), ("timeout_seconds", 11),
    ("timeout_seconds", True),
])
def test_delivery_configuration_is_strict(field, value):
    with pytest.raises(NotificationDeliveryError):
        config(**{field: value})


def test_dry_run_flag_must_be_a_boolean():
    with pytest.raises(NotificationDeliveryError):
        deliver_status_notification(notice(), config(), dry_run=1)


def test_endpoint_is_not_exposed_in_config_repr_or_result():
    destination = config()
    assert URL not in repr(destination)
    assert HOST not in repr(destination)
    assert PUBLIC_TEST_IP not in repr(destination)
    assert URL not in repr(deliver_status_notification(notice(), destination))


@pytest.mark.parametrize("status", [301, 400, 503, True, "204"])
def test_non_2xx_or_invalid_response_is_not_reported_as_delivery(status):
    with pytest.raises(NotificationDeliveryError) as caught:
        deliver_status_notification(notice(), config(enabled=True), dry_run=False,
                                    transport=lambda *_args: status)
    assert URL not in str(caught.value)


def test_transport_exception_is_sanitized_and_not_retried():
    calls = []

    def failing_transport(*_args):
        calls.append(1)
        raise RuntimeError("SYNTHETIC-SECRET-CONTEXT")

    with pytest.raises(NotificationDeliveryError) as caught:
        deliver_status_notification(notice(), config(enabled=True), dry_run=False,
                                    transport=failing_transport)
    assert calls == [1]
    assert "SYNTHETIC-SECRET-CONTEXT" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("forgery", [
    lambda n: StatusNotification(n.payload_json, n.text + " APPROVED"),
    lambda n: StatusNotification(n.payload_json + " ", n.text),
    lambda n: StatusNotification(n.payload_json.replace('"review_needed"', '"approved"'), n.text),
    lambda n: StatusNotification(n.payload_json[:-1] + ',"message":"SYNTHETIC"}', n.text),
])
def test_forged_content_is_refused_before_transport(forgery):
    calls = []
    with pytest.raises(NotificationDeliveryError):
        deliver_status_notification(forgery(notice()), config(enabled=True), dry_run=False,
                                    transport=lambda *_args: calls.append(1))
    assert calls == []


@pytest.mark.parametrize("private_ip", [
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "::1",
])
def test_private_ip_blocks_before_socket_connection(monkeypatch, private_ip):

    def forbidden(*_args, **_kwargs):
        raise AssertionError("socket opened")

    monkeypatch.setattr(adapter.socket, "socket", forbidden)
    with pytest.raises(NotificationDeliveryError, match="blocked"):
        adapter._send_https(HOST, "/synthetic-hook", private_ip, b"{}", 3)


def test_pinned_public_ip_uses_socket_timeout_without_dns(monkeypatch):
    calls = []

    class FakeSocket:
        def settimeout(self, seconds):
            calls.append(("timeout", seconds))

        def connect(self, address):
            calls.append(("connect", address))
            raise RuntimeError("synthetic stop before network")

        def close(self):
            calls.append(("close",))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("DNS lookup occurred")

    monkeypatch.setattr(adapter.socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(adapter.socket, "socket", lambda *_args: FakeSocket())
    with pytest.raises(RuntimeError, match="synthetic stop"):
        adapter._send_https(HOST, "/synthetic-hook", PUBLIC_TEST_IP, b"{}", 3)
    assert calls == [("timeout", 3), ("connect", (PUBLIC_TEST_IP, 443)), ("close",)]
