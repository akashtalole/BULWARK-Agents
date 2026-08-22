import asyncio

from bulwark.agents.drift_sentinel import reopen_assessment
from bulwark.agents.remediation_router import _tickets, open_ticket
from bulwark.platform.models import Finding, finding_repo, vendor_repo
from bulwark.platform.rollback import rollback_ledger, rollback_trace


def test_reopen_assessment_records_a_compensating_action():
    vendor = vendor_repo.get_or_create("acme-eu", "Rollback Vendor A")
    asyncio.run(reopen_assessment(vendor.vendor_id, "test", "medium", "trace_rollback_a"))

    actions = rollback_ledger.list_for_trace("trace_rollback_a")
    assert len(actions) == 1
    assert actions[0].action_type == "reopen_assessment"
    assert actions[0].subject_id == vendor.vendor_id
    assert actions[0].before_value == "onboarding"


def test_open_ticket_records_a_compensating_action():
    finding_repo.create(
        Finding(finding_id="find_rollback_tix", tenant="acme-eu", vendor_id="v1", control_ref="CC6.1", status="gap",
                gap_description="x", residual_risk=5, evidence_ids=[], assertion_ids=[], trace_id="trace_rollback_b")
    )
    result = open_ticket("find_rollback_tix", "security-review-queue", "follow up")

    actions = rollback_ledger.list_for_trace("trace_rollback_b")
    assert len(actions) == 1
    assert actions[0].action_type == "open_ticket"
    assert actions[0].subject_id == result["ticket_id"]


def test_rollback_trace_reverts_vendor_status():
    vendor = vendor_repo.get_or_create("acme-eu", "Rollback Vendor B")
    asyncio.run(reopen_assessment(vendor.vendor_id, "test", "high", "trace_rollback_c"))
    assert vendor_repo.get(vendor.vendor_id).status == "under_review"

    reverted = rollback_trace("trace_rollback_c")

    assert len(reverted) == 1
    assert vendor_repo.get(vendor.vendor_id).status == "onboarding"


def test_rollback_trace_reverts_ticket_status():
    finding_repo.create(
        Finding(finding_id="find_rollback_tix2", tenant="acme-eu", vendor_id="v1", control_ref="CC6.1", status="gap",
                gap_description="x", residual_risk=5, evidence_ids=[], assertion_ids=[], trace_id="trace_rollback_d")
    )
    result = open_ticket("find_rollback_tix2", "security-review-queue", "follow up")
    assert _tickets.get(result["ticket_id"])["status"] == "open"

    rollback_trace("trace_rollback_d")

    assert _tickets.get(result["ticket_id"])["status"] == "not_opened"


def test_rollback_is_idempotent_second_call_is_noop():
    vendor = vendor_repo.get_or_create("acme-eu", "Rollback Vendor C")
    asyncio.run(reopen_assessment(vendor.vendor_id, "test", "low", "trace_rollback_e"))

    first = rollback_trace("trace_rollback_e")
    second = rollback_trace("trace_rollback_e")

    assert len(first) == 1
    assert second == []


def test_rollback_replays_multiple_actions_in_reverse_order():
    vendor = vendor_repo.get_or_create("acme-eu", "Rollback Vendor D")
    finding_repo.create(
        Finding(finding_id="find_rollback_multi", tenant="acme-eu", vendor_id=vendor.vendor_id, control_ref="CC6.1",
                status="gap", gap_description="x", residual_risk=5, evidence_ids=[], assertion_ids=[], trace_id="trace_rollback_f")
    )
    asyncio.run(reopen_assessment(vendor.vendor_id, "test", "medium", "trace_rollback_f"))
    open_ticket("find_rollback_multi", "security-review-queue", "follow up")

    reverted = rollback_trace("trace_rollback_f")

    assert [r["action_type"] for r in reverted] == ["open_ticket", "reopen_assessment"]  # most recent first
