"""Mechanically enforces the decoupling claim `agents/orchestrator.py`'s
own module docstring makes: "No agent module imports another agent
module." That claim is only worth anything if something actually breaks
when it stops being true -- this is that something, an AST-based scan
rather than a grep, so a multi-line or aliased import can't quietly slip
past it the way one already had (see `agents/drift_sentinel.py`'s
history: it used to import `agents/offboarding.py`'s
`check_offboarding_overdue` directly, a plain synchronous function call
bypassing both ADK's own composition primitives and the event bus -- this
test would have caught that).

Two carve-outs, both narrow and named:

- `orchestrator.py` is exempt entirely -- it is the one file allowed to
  know about every agent, that's what makes it the composition root.
- Importing another registered agent module's `<name>_agent` object
  (the ADK `LlmAgent` instance every agent module defines) is allowed,
  because that's `supervisor.py`'s `sub_agents=[...]` delegation -- a
  first-class ADK mechanism, not a hand-rolled bypass. Importing anything
  *else* from a sibling agent module (a plain function, a helper, a
  constant) is exactly the bypass this test exists to catch, because it
  means one agent's deterministic logic is reaching into another agent's
  implementation directly instead of going through the event bus or an
  ADK-sanctioned handoff.
"""

from __future__ import annotations

import ast
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "src" / "bulwark" / "agents"

# Every module in agents/ that corresponds to a registered AgentRecord in
# platform/registry.py. Cross-imports between these -- other than through
# orchestrator.py, or of the sibling's own `_agent` object -- are the
# violation this test exists to catch.
REGISTERED_AGENT_MODULES = {
    "supervisor",
    "intake",
    "contract_intelligence",
    "concentration_analyzer",
    "framework_crosswalk",
    "offboarding",
    "executive_digest",
    "evidence_collector",
    "risk_assessor",
    "questionnaire_responder",
    "drift_sentinel",
    "remediation_router",
}

# The composition root: allowed to import any agent module directly.
EXEMPT_MODULES = {"orchestrator"}


def _imported_names_by_bulwark_agent_submodule(tree: ast.Module) -> dict[str, set[str]]:
    """Maps each imported `bulwark.agents.<submodule>` to the set of
    names pulled from it, so a `<name>_agent` import (ADK sub_agents
    delegation) can be told apart from a plain function/helper import."""
    found: dict[str, set[str]] = {}
    prefix = "bulwark.agents."
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(prefix):
            submodule = node.module[len(prefix):].split(".")[0]
            found.setdefault(submodule, set()).update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(prefix):
                    submodule = alias.name[len(prefix):].split(".")[0]
                    found.setdefault(submodule, set())
    return found


def test_no_registered_agent_module_imports_another():
    violations: list[str] = []
    for path in sorted(AGENTS_DIR.glob("*.py")):
        module_name = path.stem
        if module_name not in REGISTERED_AGENT_MODULES or module_name in EXEMPT_MODULES:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for imported_module, names in _imported_names_by_bulwark_agent_submodule(tree).items():
            if imported_module not in REGISTERED_AGENT_MODULES or imported_module == module_name:
                continue
            non_agent_object_names = {n for n in names if not n.endswith("_agent")}
            if non_agent_object_names or not names:
                violations.append(
                    f"{module_name}.py imports {sorted(non_agent_object_names) or '(the module itself)'} "
                    f"from agent module '{imported_module}' directly"
                )

    assert not violations, (
        "Direct agent-to-agent imports found (other than a sibling's ADK `_agent` object "
        "for sub_agents delegation) -- route these through the event bus or through "
        "agents/orchestrator.py (the composition root) instead:\n" + "\n".join(violations)
    )
