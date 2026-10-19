"""
agent/nodes/finance_checker.py — 6D: Budget Availability via pgvector RAG
==========================================================================
Generates a 1024-dim Nvidia embedding of the task description, then runs
a cosine-similarity search against the finance_budgets table using the
match_finance_budgets Supabase RPC function.

If a semantically matching category is found with budget_remaining <= 0,
a finance_flag is raised on the task.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict

from dotenv import load_dotenv
from supabase import create_client, Client

from agent.llm_client import get_embedding
from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

FINANCE_SIMILARITY_THRESHOLD = 0.50


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    return create_client(url, key)


def _time_ago(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        seconds = int(diff.total_seconds())
        if seconds < 3600:
            return f"{seconds // 60} mins ago"
        elif seconds < 86400:
            return f"{seconds // 3600} hours ago"
        return f"{seconds // 86400} days ago"
    except Exception:
        return "recently"


def finance_checker_node(state: AgentState) -> dict:
    """
    Semantic budget check for each task.

    For each task:
      1. Embed: title + " " + resource_type
      2. Call match_finance_budgets RPC (threshold=0.70)
      3. If top match has budget_remaining <= 0 → raise finance_flag

    Returns:
        Partial tasks dict: {task_id: {"finance_flag": ..., "finance_provenance": ...}}
    """
    supabase = _get_supabase()
    tasks = state.get("tasks", {})
    updates: Dict[str, dict] = {}

    for task_id, task in tasks.items():
        title = task.get("title", "")
        resource_type = task.get("resource_type", "unknown")
        search_text = f"{title} {resource_type}".strip()

        # ── Generate embedding ───────────────────────────────────────────
        try:
            embedding = get_embedding(search_text)
        except Exception as exc:
            logger.error(
                "finance_checker_node: embedding failed for task '%s': %s",
                task_id, exc,
            )
            continue

        # ── Call pgvector RPC ────────────────────────────────────────────
        try:
            result = supabase.rpc(
                "match_finance_budgets",
                {
                    "query_embedding": embedding,
                    "match_threshold": FINANCE_SIMILARITY_THRESHOLD,
                    "match_count": 3,
                },
            ).execute()
        except Exception as exc:
            logger.error(
                "finance_checker_node: RPC failed for task '%s': %s",
                task_id, exc,
            )
            continue

        if not result.data:
            logger.debug(
                "finance_checker_node: no budget match for task '%s' (text: '%s…').",
                task_id, search_text[:60],
            )
            continue

        # ── Evaluate top match ───────────────────────────────────────────
        top = result.data[0]
        category: str = top.get("category", "unknown")
        budget_remaining: float = float(top.get("budget_remaining", 1.0))
        currency: str = top.get("currency", "USD")
        similarity: float = float(top.get("similarity", 0.0))
        owner: str = top.get("owner", "unknown")

        logger.info(
            "finance_checker_node: task '%s' → category='%s' "
            "budget_remaining=%s similarity=%.3f",
            task_id, category, budget_remaining, similarity,
        )

        if budget_remaining <= 0:
            finance_flag = (
                f"Budget ${budget_remaining:.0f} {currency} for category: {category}"
            )
            finance_provenance = (
                f"Google Sheets · Q3 Budget tab · category: {category} "
                f"· owner: {owner} · similarity {similarity:.2f}"
            )
            logger.warning(
                "finance_checker_node: 🚨 task '%s' flagged — %s",
                task_id, finance_flag,
            )
            updates[task_id] = {
                "finance_flag": finance_flag,
                "finance_provenance": finance_provenance,
            }

    return {"tasks": updates}
