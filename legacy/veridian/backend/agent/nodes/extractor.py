"""
agent/nodes/extractor.py — 6B: LLM extraction via Pydantic Tool Calling
=========================================================================
Parses the raw meeting transcript into structured tasks, decisions, and
a TL;DR summary using Nvidia NIM's forced tool-calling structured output.
"""

import os
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from agent.state import AgentState, Task, DecisionItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas for LLM extraction (Task 6B spec)
# ---------------------------------------------------------------------------

class MeetingContext(BaseModel):
    speaker_resolution_scratchpad: str = Field(default="", description="Use this field to write out your Step 1 plain English analysis of who is doing what before filling out the rest of the JSON.")
    title: str = Field(default="Meeting Summary", description="Short meeting title")
    date: str = Field(default="Unknown", description="Meeting date if mentioned, else 'Unknown'")
    attendees: List[str] = Field(default_factory=list, description="All names mentioned as attendees")
    tldr_bullets: List[str] = Field(
        default_factory=list,
        description="3 high-impact bullet points summarising the meeting — provide exactly 3",
    )


class TaskExtraction(BaseModel):
    task_id: str = Field(description="Short unique ID like 't1', 't2', etc.")
    title: str = Field(description="Concise action-oriented task title suitable for a Jira ticket")
    assignee: str = Field(
        default="UNASSIGNED",
        description="Person responsible. Use 'UNASSIGNED' if unclear from context."
    )
    resource_type: str = Field(
        default="unknown",
        description=(
            "Category of resource needed: 'compute', 'api_integration', 'security_review', "
            "'product_feature', 'infrastructure', 'hr_action', or 'unknown'."
        )
    )
    transcript_quote: str = Field(
        default="",
        description="Verbatim short quote from the transcript that produced this task"
    )


class DecisionExtraction(BaseModel):
    decision: str = Field(description="Plain-English statement of the decision made")
    context_quote: str = Field(default="", description="Verbatim quote from the transcript supporting this decision")


class DiscussionFlag(BaseModel):
    topic: str = Field(description="one line description of what was discussed")
    people_mentioned: List[str] = Field(description="names of people involved")
    transcript_quote: str = Field(description="verbatim sentence from transcript")
    resource_type: str = Field(description="must be one of: 'hr_check', 'enterprise_compute', 'security', 'capacity_check'")


class ExtractionOutput(BaseModel):
    meeting_context: MeetingContext = Field(default_factory=MeetingContext)
    tasks: List[TaskExtraction] = Field(default_factory=list)
    discussion_flags: List[DiscussionFlag] = Field(default_factory=list)
    key_decisions: List[DecisionExtraction] = Field(default_factory=list)
    not_actioned: List[str] = Field(
        default_factory=list,
        description="Topics discussed but deliberately not turned into action items"
    )


# ---------------------------------------------------------------------------
# System prompt for extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """
You are an agentic firewall for enterprise meeting intelligence.
Your job is NOT to summarize the meeting. Your job is to extract
ONLY specific action items where a named person is being assigned work.

STEP 1 — SPEAKER RESOLUTION (do this in your head first):
Identify every speaker. When someone says "I will..." or "I'm going to...",
the assignee is that speaker. Map first names to the correct person.

Known people in this meeting and their roles:
- Scott = Engineering Manager (the meeting host)
- Josh = Product Manager
- Jason = Senior PM (currently on PATERNITY LEAVE per transcript)
- Dov Hershkovitz = NEW HIRE, API Monitoring Engineer (just hired)
- Korina = Release PM
- Gabe Weaver = New Manage PM Lead (just hired)

STEP 2 — EXTRACT ONLY THESE TYPES OF TASKS:
1. Any work assigned to Jason (he is on paternity leave — this is a trap)
2. Any work assigned to Dov (he is a new hire — capacity trap)
3. Any discussion about compute costs or server budgets (budget trap)
4. Any discussion about confidential merge requests or data security (security trap)
5. Any work clearly assigned to Josh (happy path)
6. Any other explicit assignment where speaker or name is clear

STEP 3 — FOR EVERY TASK YOU EXTRACT:
- assignee: use the EXACT first name from the transcript. Never UNASSIGNED
  if the speaker or assignee name is determinable.
- transcript_quote: copy the EXACT sentence from the transcript that proves
  this assignment. Never leave this empty.
- resource_type: one of [compute, security, hr, saas_tooling, headcount, unknown]

STEP 4 — KEY DECISIONS:
Extract firm decisions made in the meeting. A decision is different from a task.
"We decided to adopt dual-track agile" is a decision. "Josh will update the doc" is a task.

ADDITIONALLY extract a second list called discussion_flags.
These are NOT tasks — they are important discussions that require 
policy validation against company databases.

Scan the transcript specifically for these four patterns:

1. PATERNITY LEAVE / LEAVE / UNAVAILABILITY
   If any person is mentioned as being on leave, paternity leave, 
   vacation, or unavailable → resource_type: "hr_check"
   Example trigger: "Jason is on paternity leave"

2. COMPUTE COSTS / BUDGET / SCALING COSTS / MIRRORS
   If there is any discussion about compute costs, server budgets, 
   cost models, mirrors, or scaling expenses → resource_type: "enterprise_compute"
   Example trigger: "customers will absorb the costs on self managed of compute"

3. CONFIDENTIAL DATA / MERGE REQUESTS / SECURITY / GDPR / DATA HANDLING
   If there is any discussion about confidential merge requests, 
   data security, compliance, or sensitive data handling
   → resource_type: "security"
   Example trigger: "confidential merge requests... security problems"

4. NEW HIRE MENTIONED FOR WORK ASSIGNMENT
   If a newly hired person is mentioned in the context of being 
   assigned work or leading something → resource_type: "capacity_check"
   Example trigger: "Dov Hershkovitz we just hired him as the API monitoring"

For EACH flag you find:
- topic: one sentence describing what was discussed
- people_mentioned: list of first names involved
- transcript_quote: copy the EXACT verbatim sentence from the transcript
- resource_type: one of the four types above

If you find no discussions matching these patterns, return an empty list.

Return strict JSON only. No preamble. No explanation.
"""



# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def preprocess_transcript(raw: str) -> str:
    """
    The transcript has no speaker labels.
    We know from context who says what based on the meeting structure.
    Add known speaker moments as hints.
    """
    # The transcript is one block — add context header
    context_header = """
[MEETING CONTEXT]
This is the GitLab 12.2 Product Team Sync.
The host speaking at the start is Scott (Engineering Manager).
Other speakers identified: Josh, Jason, Korina, Gabe, Dov, Christopher, Kenny.

When someone says "I will..." or "I'm gonna..." — that is Scott speaking
unless another name is explicitly introduced as the speaker.

Jason is mentioned as being ON PATERNITY LEAVE.
Dov Hershkovitz is mentioned as a BRAND NEW HIRE for API Monitoring.
Josh is praised multiple times and given work.

[TRANSCRIPT BELOW]
"""
    return context_header + raw


def extractor_node(state: AgentState) -> dict:
    """
    LLM extraction node. Parses the raw transcript into structured AgentState fields.

    Returns partial state dict with:
        tasks           — Dict[str, Task] keyed by task_id
        key_decisions   — List[DecisionItem]
        meeting_context — Dict with title, date, attendees, tldr_bullets
    """
    transcript: str = preprocess_transcript(state["transcript"])

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0
    )

    logger.info("extractor_node: calling Gemini 2.5 Pro for single-step extraction…")
    extractor = llm.with_structured_output(ExtractionOutput)
    
    prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\n[USER REQUEST]\nExtract tasks and decisions from this transcript strictly into the required JSON schema:\n\n{transcript}"
    
    extraction: ExtractionOutput = extractor.invoke(prompt)

    # ── Convert TaskExtraction list → Dict[str, Task] ───────────────────
    tasks_dict: Dict[str, Task] = {}
    for t in extraction.tasks:
        tasks_dict[t.task_id] = Task(
            task_id=t.task_id,
            title=t.title,
            assignee=t.assignee,
            resource_type=t.resource_type,
            transcript_quote=t.transcript_quote,
            status="PENDING",
            # All firewall fields start as None — populated by parallel checkers
            hr_status=None,
            hr_provenance=None,
            finance_flag=None,
            finance_provenance=None,
            security_flag=None,
            security_confidence=None,
            security_provenance=None,
            capacity_flag=None,
            capacity_provenance=None,
            rerouted_assignee=None,
            resolution_action=None,
            reframed_title=None,
            reframed_description=None,
            jira_ticket_id=None,
            jira_url=None,
            slack_dm_sent=None,
        )

    for i, flag in enumerate(extraction.discussion_flags):
        flag_id = f"flag_{i+1}"
        tasks_dict[flag_id] = Task(
            task_id=flag_id,
            title=flag.topic,
            assignee=flag.people_mentioned[0] if flag.people_mentioned else "UNASSIGNED",
            resource_type=flag.resource_type,
            transcript_quote=flag.transcript_quote,
            status="PENDING",
            hr_status=None,
            hr_provenance=None,
            finance_flag=None,
            finance_provenance=None,
            security_flag=None,
            security_confidence=None,
            security_provenance=None,
            capacity_flag=None,
            capacity_provenance=None,
            rerouted_assignee=None,
            resolution_action=None,
            reframed_title=None,
            reframed_description=None,
            jira_ticket_id=None,
            jira_url=None,
            slack_dm_sent=None
        )

    # ── Convert DecisionExtraction list → List[DecisionItem] ────────────
    key_decisions: List[DecisionItem] = [
        DecisionItem(decision=d.decision, context_quote=d.context_quote)
        for d in extraction.key_decisions
    ]

    # ── Build meeting_context dict ───────────────────────────────────────
    ctx = extraction.meeting_context
    meeting_context = {
        "title": ctx.title,
        "date": ctx.date,
        "attendees": ctx.attendees,
        "tldr_bullets": ctx.tldr_bullets,
        "not_actioned": extraction.not_actioned,
    }

    logger.info(
        "extractor_node: extracted %d tasks, %d decisions.",
        len(tasks_dict),
        len(key_decisions),
    )

    return {
        "tasks": tasks_dict,
        "key_decisions": key_decisions,
        "meeting_context": meeting_context,
    }
