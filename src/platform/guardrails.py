"""Model Armor: guardrails against prompt injection, tool poisoning, and
PII leakage, placed at every boundary where untrusted content enters or
leaves the fleet (section 6.2):

1. **Inbound artifacts** -- Intake Agent's before_model_callback, on
   vendor-supplied documents. This is the thirty-second demo moment: a
   poisoned vendor PDF containing an injection payload gets caught before
   the model ever reasons over it, and the block is logged as a security
   event, not silently dropped.
2. **Tool arguments** -- before_tool_callback, fleet-wide, in case an
   injection payload survives into a function-call argument instead of
   free text.
3. **Model output** -- after_model_callback, fleet-wide PII redaction.
4. **Outbound answers** -- a DLP-style scan on Questionnaire Responder's
   drafted answers specifically (``scan_for_dlp_violation`` below),
   applied before an answer can be marked exportable, standing in for a
   real Cloud DLP inspection job in production.

Implemented as one ADK ``BasePlugin`` attached once to the shared
``Runner`` so every one of the seven agents gets it uniformly -- an agent
added to the fleet later cannot forget to import guardrails, because it
was never given the choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from google.adk.plugins.base_plugin import BasePlugin

from bulwark.platform.observability import audit_log

_INJECTION_PATTERNS = [
    r"ignore (all|any|the)? ?(previous|prior|above) instructions",
    r"disregard (all|any|the)? ?(previous|prior|above) (instructions|rules|prompt)",
    r"you are now (in )?(developer|dan|jailbreak|unrestricted) mode",
    r"reveal (your|the) (system|hidden) prompt",
    r"act as if you have no (restrictions|guardrails|rules)",
    r"</?(system|admin|tool_result|function_results)>",
    r"override (your|the) (instructions|guardrails|safety)",
    r"mark (this|the) (vendor|control|finding) as (satisfied|compliant|passed) regardless",
    r"grant (full|admin|root) access",
    r"do anything now",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "api_key_like": re.compile(r"\b(?:sk|AKIA|ghp|xox[baprs])[A-Za-z0-9_-]{12,}\b"),
    "internal_hostname": re.compile(r"\b[a-z0-9-]+\.(?:internal|corp|prod)\.[a-z]{2,}\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class ScanResult:
    blocked: bool
    reason: str | None = None
    matched_pattern: str | None = None


def scan_for_injection(text: str) -> ScanResult:
    for pattern in _INJECTION_RE:
        if pattern.search(text):
            return ScanResult(blocked=True, reason="prompt_injection_detected", matched_pattern=pattern.pattern)
    return ScanResult(blocked=False)


def redact_pii(text: str) -> tuple[str, list[str]]:
    redacted = text
    found: list[str] = []
    for kind, pattern in _PII_PATTERNS.items():
        if pattern.search(redacted):
            found.append(kind)
            redacted = pattern.sub(f"[REDACTED_{kind.upper()}]", redacted)
    return redacted, found


def scan_for_dlp_violation(text: str) -> tuple[bool, list[str]]:
    """Stand-in for a Cloud DLP inspection job on an outbound questionnaire
    answer: does this text contain anything that must never leave the
    company (internal hostnames, credential-shaped strings, customer PII)?
    Returns (blocked, kinds_found) -- callers should route a blocked
    answer to a human rather than exporting it."""
    _, found = redact_pii(text)
    sensitive = [k for k in found if k in {"api_key_like", "internal_hostname", "ssn", "credit_card"}]
    return (len(sensitive) > 0, sensitive)


def _extract_text(content) -> str:
    if content is None or not getattr(content, "parts", None):
        return ""
    return " ".join(part.text for part in content.parts if getattr(part, "text", None))


class GuardrailsPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="model_armor")

    async def before_model_callback(self, *, callback_context, llm_request):
        text = ""
        for content in getattr(llm_request, "contents", []) or []:
            text += _extract_text(content) + "\n"
        result = scan_for_injection(text)
        if result.blocked:
            audit_log.record(
                agent_name=callback_context.agent_name,
                event="model_armor_blocked_input",
                detail=f"matched pattern: {result.matched_pattern}",
                invocation_id=callback_context.invocation_id,
            )
            from google.adk.models.llm_response import LlmResponse
            from google.genai import types

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                "Blocked by Model Armor: this input matched a known "
                                "prompt-injection pattern and was not sent to the model."
                            )
                        )
                    ],
                ),
                turn_complete=True,
            )
        return None

    async def after_model_callback(self, *, callback_context, llm_response):
        content = getattr(llm_response, "content", None)
        text = _extract_text(content)
        if not text:
            return None
        redacted, found = redact_pii(text)
        if not found:
            return None
        audit_log.record(
            agent_name=callback_context.agent_name,
            event="model_armor_redacted_output",
            detail=f"redacted PII kinds: {found}",
            invocation_id=callback_context.invocation_id,
        )
        content.parts[0].text = redacted
        for part in content.parts[1:]:
            if getattr(part, "text", None):
                part.text, _ = redact_pii(part.text)
        return llm_response

    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        for value in tool_args.values():
            if isinstance(value, str):
                result = scan_for_injection(value)
                if result.blocked:
                    audit_log.record(
                        agent_name=tool_context.agent_name,
                        event="model_armor_blocked_tool_call",
                        detail=f"tool={tool.name} matched pattern: {result.matched_pattern}",
                        invocation_id=tool_context.invocation_id,
                    )
                    return {
                        "error": "blocked_by_model_armor",
                        "reason": "tool argument matched a prompt-injection pattern",
                    }
        return None


guardrails_plugin = GuardrailsPlugin()
