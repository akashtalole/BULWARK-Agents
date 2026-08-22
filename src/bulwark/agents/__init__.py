"""The seven-agent fleet. Every tool function below calls
``identity.require_grant`` and ``policy.enforce_autonomy`` before it
touches state -- the zero-trust and kill-switch properties are enforced
in this code, not asserted by an agent's prompt. ``orchestrator.py`` wires
the agents to the event bus; no agent module here ever imports or calls
another agent module directly.
"""
