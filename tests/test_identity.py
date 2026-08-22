import pytest

from bulwark.platform.identity import PermissionDenied, require_grant


def test_intake_may_write_assertions():
    require_grant("vendor-intake", "assertions:write")  # must not raise


def test_intake_may_not_read_evidence():
    """The core zero-trust property: the agent that touches untrusted
    input has no access to anything worth stealing."""
    with pytest.raises(PermissionDenied):
        require_grant("vendor-intake", "evidence:read")


def test_intake_may_not_write_findings():
    with pytest.raises(PermissionDenied):
        require_grant("vendor-intake", "findings:write")


def test_evidence_collector_may_not_write_findings():
    with pytest.raises(PermissionDenied):
        require_grant("evidence-collector", "findings:write")


def test_risk_assessor_may_not_read_quarantine_gcs():
    with pytest.raises(PermissionDenied):
        require_grant("risk-assessor", "gcs:quarantine:read")


def test_remediation_router_has_no_autonomous_send_scope():
    """There is no "email:send_autonomous" scope granted to anyone -- the
    capability doesn't exist in this codebase, not just the permission."""
    with pytest.raises(PermissionDenied):
        require_grant("remediation-router", "email:send_autonomous")


def test_unknown_agent_has_no_grants_at_all():
    with pytest.raises(PermissionDenied):
        require_grant("some-agent-that-does-not-exist", "assertions:write")
