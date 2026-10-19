"""
agent/nodes/security_checker.py — 6E: Policy Enforcement via pgvector RAG
==========================================================================
Generates a 1024-dim embedding of the task description + transcript quote,
then runs a cosine-similarity search against security_policies using the
match_security_policies Supabase RPC function.

If similarity > 0.75, the task violates corporate policy and is flagged.
"""

import logging
import os
from typing import Dict

from dotenv import load_dotenv
from supabase import create_client, Client

from agent.llm_client import get_embedding
from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

SECURITY_SIMILARITY_THRESHOLD = 0.50


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    return create_client(url, key)


def security_checker_node(state: AgentState) -> dict:
    """
    RAG-based policy enforcement for each task.

    For each task:
      1. Embed: title + " " + transcript_quote
      2. Call match_security_policies RPC (threshold=0.75)
      3. If match → raise security_flag with policy_id and chunk preview

    Returns:
        Partial tasks dict with security_flag, security_confidence,
        and security_provenance for flagged tasks.
    """
    supabase = _get_supabase()
    tasks = state.get("tasks", {})
    updates: Dict[str, dict] = {}

    for task_id, task in tasks.items():
        title = task.get("title", "")
        transcript_quote = task.get("transcript_quote", "")
        search_text = f"{title} {transcript_quote}".strip()

        # ── Generate embedding ───────────────────────────────────────────
        try:
            embedding = get_embedding(search_text)
        except Exception as exc:
            logger.error(
                "security_checker_node: embedding failed for task '%s': %s",
                task_id, exc,
            )
            continue

        # ── Call pgvector RPC ────────────────────────────────────────────
        try:
            result = supabase.rpc(
                "match_security_policies",
                {
                    "query_embedding": embedding,
                    "match_threshold": SECURITY_SIMILARITY_THRESHOLD,
                    "match_count": 3,
                },
            ).execute()
        except Exception as exc:
            logger.error(
                "security_checker_node: RPC failed for task '%s': %s",
                task_id, exc,
            )
            continue

        if not result.data:
            logger.debug(
                "security_checker_node: no policy match for task '%s'.",
                task_id,
            )
            continue

        # ── Evaluate top match ───────────────────────────────────────────
        top = result.data[0]
        policy_id: str = top.get("policy_id") or "POLICY-UNKNOWN"
        chunk_text: str = top.get("chunk_text", "")
        document_name: str = top.get("document_name", "security-policy.pdf")
        similarity: float = float(top.get("similarity", 0.0))

        # First 50 chars of chunk as preview
        chunk_preview = chunk_text[:50].strip()
        if len(chunk_text) > 50:
            chunk_preview += "…"

        security_flag = f"Violates {policy_id}: {chunk_preview}"
        security_provenance = (
            f"RAG · {policy_id} · similarity {similarity:.2f} · {document_name}"
        )

        logger.warning(
            "security_checker_node: 🚨 task '%s' flagged — %s (similarity=%.3f)",
            task_id, security_flag, similarity,
        )

        updates[task_id] = {
            "security_flag": security_flag,
            "security_confidence": similarity,
            "security_provenance": security_provenance,
        }

    return {"tasks": updates}
