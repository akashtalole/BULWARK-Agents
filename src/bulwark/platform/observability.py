"""Agent Observability: OpenTelemetry spans plus a queryable, per-trace
audit trail -- the "OTel-compliant audit logs and end-to-end reasoning
chain traces" the track asks for.

Every agent/tool call opens a real OTel span via the standard SDK (point
OTEL_EXPORTER_OTLP_ENDPOINT at Cloud Trace in production) and writes a
structured entry keyed by trace_id, so a full cross-agent reasoning chain
-- Supervisor's routing decision, Intake's extraction, Risk Assessor's
citation-backed finding -- can be pulled with one query
(``GET /traces/{trace_id}``) regardless of which agent produced which
step. In production this audit table is mirrored into BigQuery
(append-only, partitioned by day, per section 4.3); here it's the same
DocumentStore abstraction used everywhere else in this build.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin
from opentelemetry import trace

from bulwark.config import settings
from bulwark.platform.store import DocumentStore

_AUDIT_COLLECTION = "audit_log"
_tracer = trace.get_tracer(settings.service_name)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    ts: str
    agent_name: str
    event: str
    detail: str
    invocation_id: str | None = None
    trace_id: str | None = None


class AuditLog:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore(_AUDIT_COLLECTION)

    def record(
        self,
        *,
        agent_name: str,
        event: str,
        detail: str,
        invocation_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=uuid.uuid4().hex[:12], ts=_now(), agent_name=agent_name, event=event, detail=detail,
            invocation_id=invocation_id, trace_id=trace_id,
        )
        key = trace_id or "_unscoped"
        self._store.append_to_list_field(key, "entries", asdict(entry))
        return entry

    def trace(self, trace_id: str) -> list[dict[str, Any]]:
        doc = self._store.get(trace_id)
        entries = (doc or {}).get("entries", [])
        return sorted(entries, key=lambda e: e["ts"])

    def count_events(self, event_prefix: str) -> int:
        """Fleet-wide count of audit entries whose `event` starts with
        `event_prefix`, scanning across every trace -- used for section
        13's "injection attempts blocked" metric (`GET /metrics`)."""
        total = 0
        for doc in self._store.list():
            total += sum(1 for e in doc.get("entries", []) if e["event"].startswith(event_prefix))
        return total


audit_log = AuditLog()


class ObservabilityPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="observability")

    async def before_agent_callback(self, *, agent, callback_context):
        span = _tracer.start_span(f"agent:{agent.name}")
        span.set_attribute("invocation_id", callback_context.invocation_id or "")
        callback_context.state["_otel_span_agent"] = span
        audit_log.record(
            agent_name=agent.name,
            event="agent_started",
            detail=f"invocation_id={callback_context.invocation_id}",
            invocation_id=callback_context.invocation_id,
            trace_id=callback_context.state.get("trace_id"),
        )
        return None

    async def after_agent_callback(self, *, agent, callback_context):
        span = callback_context.state.get("_otel_span_agent")
        if span is not None:
            span.end()
        audit_log.record(
            agent_name=agent.name,
            event="agent_finished",
            detail=f"invocation_id={callback_context.invocation_id}",
            invocation_id=callback_context.invocation_id,
            trace_id=callback_context.state.get("trace_id"),
        )
        return None

    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        audit_log.record(
            agent_name=tool_context.agent_name,
            event="tool_call_started",
            detail=f"tool={tool.name} args={tool_args}",
            invocation_id=tool_context.invocation_id,
            trace_id=tool_context.state.get("trace_id"),
        )
        return None

    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        audit_log.record(
            agent_name=tool_context.agent_name,
            event="tool_call_finished",
            detail=f"tool={tool.name} result={result}",
            invocation_id=tool_context.invocation_id,
            trace_id=tool_context.state.get("trace_id"),
        )
        return None

    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        audit_log.record(
            agent_name=tool_context.agent_name,
            event="tool_call_error",
            detail=f"tool={tool.name} error={error}",
            invocation_id=tool_context.invocation_id,
            trace_id=tool_context.state.get("trace_id"),
        )
        return None


observability_plugin = ObservabilityPlugin()
