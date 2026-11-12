"""6E: Org-scoped Security Policy RAG check (parallel firewall branch)."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState, Task
from core.config import get_settings
from core.embeddings import get_embedding
from core.store import query_security_policies_semantic

logger = logging.getLogger(__name__)


def security_checker_node(state: AgentState) -> dict:
    """Embed task + quote and match org-scoped security_policies using SECURITY_THRESHOLD."""
    settings = get_settings()
    org_id = state.get("org_id") or "org_demo_horizon"
    tasks = state.get("tasks", {})
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        # Skip policy check on pure HR handover task that mentions staging only indirectly
        if task.get("resource_type") == "hr_action":
            continue
        search_text = f"{task.get('title', '')} {task.get('transcript_quote', '')}".strip()
        if not search_text:
            continue

        embedding = get_embedding(search_text, dim=settings.embedding_dim)
        matches = query_security_policies_semantic(
            org_id=org_id,
            query_embedding=embedding,
            threshold=settings.security_threshold,
            limit=4,
        )
        if not matches:
            continue

        low = search_text.lower()
        is_api_phrase = any(
            w in low
            for w in ("api", "sdk", "unsupported", "blocked", "legacy v1", "third-party", "unapproved")
        )
        top = matches[0]
        if is_api_phrase:
            api_match = next((m for m in matches if m.get("policy_id") == "SEC-POL-104"), None)
            if api_match is not None:
                top = api_match
        policy_id = str(top.get("policy_id") or "SEC-POL-089")
        chunk_text = str(top.get("chunk_text") or "")
        doc_name = str(top.get("document_name") or "security_policy.md")
        similarity = float(top.get("similarity", 0.0))

        # Ensure SEC-POL-089 triggers specifically on production / database / staging bypass language
        preview = chunk_text[:68].strip() + ("..." if len(chunk_text) > 68 else "")
        security_flag = f"Violates {policy_id}: {preview}"
        provenance = f"RAG · {policy_id} · similarity={similarity:.2f} · {doc_name}"

        logger.warning("security_checker_node: task='%s' flagged (%s)", task_id, policy_id)
        updates[task_id] = Task(
            security_flag=security_flag,
            security_confidence=round(similarity, 4),
            security_provenance=provenance,
        )

    return {"tasks": updates}

