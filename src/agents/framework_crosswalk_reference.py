"""Illustrative SOC 2 -> ISO 27001 / NIST CSF control-equivalence
crosswalk. Same labeled-mock pattern as ``contract_playbook.py`` and
``internal_sources.py``: this is a small, representative mapping, not a
certified crosswalk (a real deployment would license one, e.g. from the
Unified Compliance Framework or a Big 4 firm's own mapping, or have its
own compliance team maintain one as a Firestore collection). What's real
here is the *shape* of crosswalk-driven coverage computation
(``agents/framework_crosswalk.py``), not these specific pairings.
"""

from __future__ import annotations

# soc2_control_ref -> {target_framework: equivalent_control_ref}
CROSSWALK: dict[str, dict[str, str]] = {
    "CC6.1": {"ISO27001": "A.9.2.1", "NISTCSF": "PR.AC-1"},   # access control / MFA
    "CC6.6": {"ISO27001": "A.13.1.1", "NISTCSF": "PR.AC-5"},  # network segmentation
    "CC6.8": {"ISO27001": "A.12.4.1", "NISTCSF": "PR.PT-1"},  # logging / log retention
    "CC7.2": {"ISO27001": "A.12.4.1", "NISTCSF": "DE.CM-1"},  # security monitoring
    "CC7.3": {"ISO27001": "A.16.1.5", "NISTCSF": "RS.RP-1"},  # incident response
    "CC9.1": {"ISO27001": "A.15.1.1", "NISTCSF": "ID.SC-1"},  # vendor/third-party risk management
}


def equivalent_control(soc2_control_ref: str, target_framework: str) -> str | None:
    return CROSSWALK.get(soc2_control_ref, {}).get(target_framework)


def known_target_frameworks() -> set[str]:
    frameworks: set[str] = set()
    for targets in CROSSWALK.values():
        frameworks.update(targets.keys())
    return frameworks
