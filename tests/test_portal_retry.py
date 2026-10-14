"""The portal crawler retries server errors before a shard gives up (RR-7).

Runs 38130733364 and 37919050016 lost a whole shard each at the WSDL bootstrap: one HTTP 520
from the portal's proxy and one connection reset, neither retried. The SOAP calls retried, but
also retried a 403, which only repeats a refusal.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "simulators/justitie/scripts/import_portal.py"
spec = importlib.util.spec_from_file_location("import_portal_retry", MODULE)
portal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = portal
spec.loader.exec_module(portal)

WSDL = (
    b'<s:simpleType name="Institutie"><s:restriction>'
    b'<s:enumeration value="JudecatoriaJIBOU"/>'
    b"</s:restriction></s:simpleType>"
)


def scripted(*outcomes):
    """An urlopen that answers each request with the next outcome: a status or a body."""
    calls = []

    def urlopen(request, timeout):
        calls.append(request)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, int):
            raise urllib.error.HTTPError(request.full_url, outcome, "error", {}, None)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(outcome)

    return urlopen, calls


@pytest.fixture
def sleeps(monkeypatch):
    waited = []
    monkeypatch.setattr(portal.time, "sleep", waited.append)
    return waited


def test_wsdl_bootstrap_retries_a_520_then_succeeds(monkeypatch, sleeps):
    urlopen, calls = scripted(520, WSDL)
    monkeypatch.setattr(portal.urllib.request, "urlopen", urlopen)
    assert portal.load_courts() == ["JudecatoriaJIBOU"]
    assert len(calls) == 2
    assert sleeps == [1]


def test_wsdl_bootstrap_retries_a_connection_reset(monkeypatch, sleeps):
    urlopen, calls = scripted(ConnectionResetError(104, "reset"), WSDL)
    monkeypatch.setattr(portal.urllib.request, "urlopen", urlopen)
    assert portal.load_courts() == ["JudecatoriaJIBOU"]
    assert len(calls) == 2


def test_soap_call_retries_a_520_then_succeeds(monkeypatch, sleeps):
    urlopen, calls = scripted(520, 503, b"<response/>")
    monkeypatch.setattr(portal.urllib.request, "urlopen", urlopen)
    assert portal.call("<probe/>", "Probe") == "<response/>"
    assert len(calls) == 3
    assert sleeps == [1, 2]


def test_persistent_server_errors_fail_after_the_configured_attempts(monkeypatch, sleeps):
    urlopen, calls = scripted(520)
    monkeypatch.setattr(portal.urllib.request, "urlopen", urlopen)
    with pytest.raises(portal.PortalError, match="520"):
        portal.load_courts()
    assert len(calls) == portal.MAX_RETRIES
    assert sleeps == [2**i for i in range(portal.MAX_RETRIES - 1)]


def test_a_client_error_is_not_retried(monkeypatch, sleeps):
    urlopen, calls = scripted(403)
    monkeypatch.setattr(portal.urllib.request, "urlopen", urlopen)
    with pytest.raises(portal.PortalError, match="403"):
        portal.call("<probe/>", "Probe")
    assert len(calls) == 1
    assert sleeps == []
