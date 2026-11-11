"""6D: Org-scoped Finance Budget semantic pgvector check (parallel firewall branch)."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState, Task
from core.config import get_settings
from core.embeddings import get_embedding
from core.store import query_finance_budgets_semantic

logger = logging.getLogger(__name__)


def finance_checker_node(state: AgentState) -> dict:
    """Embed task + resource_type and query org-scoped finance_budgets using FINANCE_THRESHOLD."""
    settings = get_settings()
    org_id = state.get("org_id") or "org_demo_horizon"
    tasks = state.get("tasks", {})
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        search_text = (
            f"{task.get('title', '')} {task.get('resource_type', '')} {task.get('transcript_quote', '')}"
        ).strip()
        if not search_text:
            continue

        embedding = get_embedding(search_text, dim=settings.embedding_dim)
        matches = query_finance_budgets_semantic(
            org_id=org_id,
            query_embedding=embedding,
            threshold=settings.finance_threshold,
            limit=3,
        )
        if not matches:
            continue

        top = matches[0]
        category = str(top.get("category", "unknown"))
        budget_remaining = float(top.get("budget_remaining", 1.0))
        currency = str(top.get("currency", "INR"))
        similarity = float(top.get("similarity", 0.0))
        owner = str(top.get("owner", "Finance"))
        source = str(top.get("last_synced_from", "finance_budgets.csv"))

        if budget_remaining <= 0:
            finance_flag = f"Budget {budget_remaining:.0f} {currency} for category: {category}"
            provenance = (
                f"CSV Budget · {source} · category={category} · owner={owner} · similarity={similarity:.2f}"
            )
            logger.warning("finance_checker_node: task='%s' flagged (%s)", task_id, finance_flag)
            updates[task_id] = Task(
                finance_flag=finance_flag,
                finance_provenance=provenance,
            )

    return {"tasks": updates}
