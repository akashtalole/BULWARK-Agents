from datetime import datetime, timedelta, timezone

from bulwark.platform.memory_bank import MemoryBank


def test_new_vendor_has_empty_memory():
    bank = MemoryBank()
    memory = bank.get("vendor_never_seen")
    assert memory.negotiated_exceptions == []
    assert memory.accepted_risk_decisions == []
    assert bank.has_active_exception("vendor_never_seen", "CC6.1") is False


def test_record_assessment_persists_timestamp():
    bank = MemoryBank()
    bank.record_assessment("vendor_a")
    memory = bank.get("vendor_a")
    assert memory.vendor_id == "vendor_a"
    assert memory.last_assessment_at is not None


def test_negotiated_exception_suppresses_drift_until_expiry():
    bank = MemoryBank()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    bank.add_negotiated_exception("vendor_b", "CC6.8", "compensating control in place", future)
    assert bank.has_active_exception("vendor_b", "CC6.8") is True
    assert bank.has_active_exception("vendor_b", "CC9.9") is False


def test_expired_exception_no_longer_active():
    bank = MemoryBank()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    bank.add_negotiated_exception("vendor_c", "CC6.8", "old exception", past)
    assert bank.has_active_exception("vendor_c", "CC6.8") is False


def test_reviewer_posture_notes_accumulate_per_control():
    bank = MemoryBank()
    bank.note_reviewer_posture("vendor_d", "CC6.1", "accepted twice, stop re-flagging")
    memory = bank.get("vendor_d")
    assert memory.reviewer_posture["CC6.1"] == "accepted twice, stop re-flagging"
