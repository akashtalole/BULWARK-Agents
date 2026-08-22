"""Pub/Sub-shaped event bus: topics, dead-letter routing, and idempotency
dedup, matching the envelope contract in docs/architecture.md section 4.2.

No agent calls another agent directly anywhere in this codebase --
every inter-agent handoff is `bus.publish(topic, envelope)` and every
agent only ever `bus.subscribe(topic, handler)`s. That decoupling is
checked by tests/test_event_bus.py (publishing with zero subscribers is a
valid no-op; a failing handler never crashes the publisher).

Dispatch here is synchronous and in-process, which is what makes the
whole fleet runnable and testable without a live Pub/Sub push-endpoint
per agent. When ``USE_PUBSUB=true`` (a real GCP project + topics
provisioned by deploy/setup_gcp.sh), every publish is *also* mirrored
onto the real Pub/Sub topic, so a demo can show live topic/subscription
metrics in Cloud Console -- a full production cutover would run each
agent as its own Cloud Run push subscriber instead of in-process dispatch.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Union

from bulwark.config import settings
from bulwark.platform.store import DocumentStore

logger = logging.getLogger("bulwark.event_bus")

_DEDUP_COLLECTION = "event_dedup"
_DLQ_COLLECTION = "event_dlq"


def make_idempotency_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Envelope:
    payload: dict[str, Any]
    idempotency_key: str
    provenance: str = "internal"  # "untrusted" | "internal" | "human"
    tenant: str = field(default_factory=lambda: settings.default_tenant)
    region_pin: str = "us-central1"
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempt: int = 1
    published_at: str = field(default_factory=_now)


Handler = Callable[[str, Envelope], Union[None, Awaitable[None]]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}
        self._dedup = DocumentStore(_DEDUP_COLLECTION)
        self._dlq = DocumentStore(_DLQ_COLLECTION)
        self._pubsub_client = None
        self._pubsub_topics: dict[str, Any] = {}
        if settings.use_pubsub:
            from google.cloud import pubsub_v1  # optional dep, imported lazily

            self._pubsub_client = pubsub_v1.PublisherClient()

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subscribers.setdefault(topic, []).append(handler)

    def _already_processed(self, topic: str, envelope: Envelope) -> bool:
        key = f"{topic}:{envelope.idempotency_key}"
        if self._dedup.get(key) is not None:
            return True
        self._dedup.set(key, {"topic": topic, "event_id": envelope.event_id, "processed_at": _now()})
        return False

    def _mirror_to_real_pubsub(self, topic: str, envelope: Envelope) -> None:
        if self._pubsub_client is None:
            return
        try:
            import json

            topic_path = self._pubsub_client.topic_path(settings.gcp_project, topic)
            self._pubsub_client.publish(topic_path, json.dumps(asdict(envelope)).encode())
        except Exception:  # pragma: no cover -- best-effort demo mirroring only
            logger.warning("failed to mirror event to real Pub/Sub topic %s", topic, exc_info=True)

    def _send_to_dlq(self, topic: str, envelope: Envelope, error: Exception) -> None:
        entry = {
            "original_topic": topic,
            "envelope": asdict(envelope),
            "failure_chain": traceback.format_exc(),
            "failed_at": _now(),
        }
        self._dlq.set(f"{topic}.dlq:{envelope.event_id}", entry)
        logger.error("event %s on topic %s routed to DLQ: %s", envelope.event_id, topic, error)

    async def publish(self, topic: str, envelope: Envelope) -> None:
        """Dispatch is async because subscribers (ADK Runners) are async;
        a handler may be a plain sync function or a coroutine function --
        both are supported so cheap glue handlers don't need to bother
        with `async def` just to satisfy this signature."""
        self._mirror_to_real_pubsub(topic, envelope)

        if self._already_processed(topic, envelope):
            logger.info("skipping duplicate event %s on topic %s (idempotency)", envelope.event_id, topic)
            return

        for handler in self._subscribers.get(topic, []):
            try:
                result = handler(topic, envelope)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001 -- a bad handler must never crash the bus
                self._send_to_dlq(topic, envelope, exc)

    def dlq_entries(self, topic: str | None = None) -> list[dict[str, Any]]:
        entries = self._dlq.list()
        return [e for e in entries if topic is None or e["original_topic"] == topic]


bus = EventBus()
