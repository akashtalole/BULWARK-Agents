from datetime import datetime, timedelta, timezone

from bulwark.platform.models import (
    Artifact,
    ArtifactRepo,
    ControlRepo,
    ControlRequirement,
    Evidence,
    EvidenceRepo,
    FindingRepo,
    RunRepo,
    VendorRepo,
    FleetConfigRepo,
    Finding,
)


def test_vendor_get_or_create_is_idempotent_by_name():
    repo = VendorRepo()
    v1 = repo.get_or_create("acme-eu", "Cloudy SaaS Inc")
    v2 = repo.get_or_create("acme-eu", "Cloudy SaaS Inc")
    assert v1.vendor_id == v2.vendor_id


def test_blind_window_days_none_when_never_assessed():
    repo = VendorRepo()
    v = repo.get_or_create("acme-eu", "Never Assessed Inc")
    assert repo.blind_window_days(v) is None


def test_blind_window_days_computed_from_last_assessment():
    repo = VendorRepo()
    v = repo.get_or_create("acme-eu", "Assessed 200 Days Ago Inc")
    repo.update(v.vendor_id, last_assessed_at=(datetime.now(timezone.utc) - timedelta(days=200)).isoformat())
    assert repo.blind_window_days(repo.get(v.vendor_id)) == 200


def test_artifact_expiring_within_window():
    repo = ArtifactRepo()
    repo.create(
        Artifact(
            artifact_id="art_soon", tenant="acme-eu", vendor_id="v1", gcs_uri="gs://x", doc_type="SOC2", sha256="s",
            valid_until=(datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        )
    )
    repo.create(
        Artifact(
            artifact_id="art_later", tenant="acme-eu", vendor_id="v1", gcs_uri="gs://x", doc_type="SOC2", sha256="s2",
            valid_until=(datetime.now(timezone.utc) + timedelta(days=200)).isoformat(),
        )
    )
    expiring = repo.list_expiring_within("acme-eu", days=30)
    assert {a.artifact_id for a in expiring} == {"art_soon"}


def test_evidence_freshness_and_satisfaction():
    fresh = Evidence(
        evidence_id="ev1", tenant="acme-eu", control_ref="CC6.1", observed_value="x", expected_value="x",
        source="iam", collected_at=datetime.now(timezone.utc).isoformat(), content_hash="h",
    )
    assert fresh.freshness == "fresh"
    assert fresh.satisfied is True

    stale = Evidence(
        evidence_id="ev2", tenant="acme-eu", control_ref="CC6.1", observed_value="x", expected_value="x",
        source="iam", collected_at=(datetime.now(timezone.utc) - timedelta(days=45)).isoformat(), content_hash="h",
    )
    assert stale.freshness == "stale"
    assert stale.satisfied is False  # stale evidence never satisfies, even if values match

    mismatched = Evidence(
        evidence_id="ev3", tenant="acme-eu", control_ref="CC6.1", observed_value="a", expected_value="b",
        source="iam", collected_at=datetime.now(timezone.utc).isoformat(), content_hash="h",
    )
    assert mismatched.satisfied is False


def test_evidence_repo_latest_for_control_returns_most_recent():
    repo = EvidenceRepo()
    older = Evidence(
        evidence_id="ev_old", tenant="acme-eu", control_ref="CC9.9", observed_value="a", expected_value="a",
        source="iam", collected_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), content_hash="h",
    )
    newer = Evidence(
        evidence_id="ev_new", tenant="acme-eu", control_ref="CC9.9", observed_value="b", expected_value="b",
        source="iam", collected_at=datetime.now(timezone.utc).isoformat(), content_hash="h",
    )
    repo.create(older)
    repo.create(newer)
    assert repo.latest_for_control("acme-eu", "CC9.9").evidence_id == "ev_new"


def test_finding_human_decision_round_trip():
    repo = FindingRepo()
    repo.create(
        Finding(
            finding_id="find_test_x", tenant="acme-eu", vendor_id="v1", control_ref="CC6.1", status="gap",
            gap_description="no MFA evidence", residual_risk=10, evidence_ids=["ev1"], assertion_ids=[], trace_id="t1",
        )
    )
    assert repo.get("find_test_x").human_decision is None
    updated = repo.record_human_decision("find_test_x", "alice", "accept_risk", "compensating control exists")
    assert updated.human_decision == {
        "actor": "alice", "decision": "accept_risk", "rationale": "compensating control exists",
        "at": updated.human_decision["at"],
    }


def test_run_checkpointing_tracks_completed_and_pending_steps():
    repo = RunRepo()
    run = repo.start("drift-sentinel", ["step_a", "step_b", "step_c"])
    assert run.status == "running"
    repo.checkpoint(run.run_id, "step_a")
    mid = repo.get(run.run_id)
    assert mid.completed_steps == ["step_a"]
    assert mid.pending_steps == ["step_b", "step_c"]
    repo.checkpoint(run.run_id, "step_b")
    repo.checkpoint(run.run_id, "step_c")
    final = repo.complete(run.run_id)
    assert final.status == "completed"
    assert final.pending_steps == []


def test_fleet_config_defaults_and_updates():
    repo = FleetConfigRepo()
    config = repo.get()
    assert config.autonomy_level == 3
    assert config.paused_agents == []
    updated = repo.update(autonomy_level=0, paused_agents=["drift-sentinel"])
    assert updated.autonomy_level == 0
    assert updated.paused_agents == ["drift-sentinel"]
    repo.update(autonomy_level=3, paused_agents=[])


def test_control_repo_upsert_and_list():
    repo = ControlRepo()
    repo.upsert(
        ControlRequirement(
            control_ref="CC-TEST", tenant="acme-eu", framework="SOC2", title="Test control",
            requirement_text="...", owner="security",
        )
    )
    assert any(c.control_ref == "CC-TEST" for c in repo.list("acme-eu"))
