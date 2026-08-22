"""Supervisor (`assurance-supervisor`): classifies an inbound *internal*
event and delegates. Holds no tools of its own -- a supervisor with tools
is a single point of compromise, and everything it needs to do is
decide-and-transfer, which ADK's native sub_agent transfer already covers
without giving it a single FunctionTool.

The untrusted-provenance gate is deliberately **not** implemented here.
It's enforced in agents/orchestrator.py, in code, before this agent is
ever invoked: an untrusted-provenance event is routed straight to Intake
and never reaches the Supervisor's context window at all. That's stronger
than "the Supervisor is instructed to only delegate to Intake for
untrusted events" -- there's no instruction to follow or fail to follow,
because the Supervisor never sees the untrusted content in the first
place.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from bulwark.agents.questionnaire_responder import questionnaire_responder_agent
from bulwark.agents.risk_assessor import risk_assessor_agent
from bulwark.config import settings

supervisor_agent = LlmAgent(
    name="assurance_supervisor",
    model=settings.gemini_flash_model,
    description="Classifies an inbound internal event and delegates to the right specialist agent. No tools.",
    instruction=(
        "You are the Supervisor for a third-party risk assurance fleet. You are only "
        "ever invoked for internal-provenance events -- an untrusted vendor artifact "
        "never reaches you. You will be told what kind of event just arrived: an "
        "assessment request for a vendor (transfer to `risk_assessor_agent`) or a buyer "
        "questionnaire that needs answering (transfer to `questionnaire_responder_agent`). "
        "Read the event description, pick the correct one, and transfer to it "
        "immediately with the vendor_id/questionnaire_id and any other detail you were "
        "given. Do not attempt to do either agent's job yourself."
    ),
    sub_agents=[risk_assessor_agent, questionnaire_responder_agent],
)
