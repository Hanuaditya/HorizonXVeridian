"""Vector embedding provider with NVIDIA NIM live support and deterministic offline fallback.

Always produces unit-normalized vectors matching settings.embedding_dim (default 1024)
so pgvector HNSW queries and startup dimension checks remain uniform in both live
and offline DEMO_MODE environments.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Dict, List, Optional

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9_]+")

# Lightweight semantic synonym expansion so offline embeddings bridge phrasing
# gaps in Indian enterprise Hinglish + technical transcripts.
_CONCEPT_EXPANSIONS: Dict[str, List[str]] = {
    "production": ["prod", "staging", "bake", "deployment", "deploy", "quarantine", "release"],
    "prod": ["production", "staging", "bake", "deployment", "release"],
    "staging": ["production", "bake", "period", "14-day", "quarantine", "deploy"],
    "elastic": ["elasticsearch", "cluster", "database", "infrastructure", "aws", "deployment"],
    "elasticsearch": ["elastic", "cluster", "database", "infrastructure"],
    "cluster": ["elastic", "compute", "infra", "enterprise", "aws", "provisioning"],
    "database": ["db", "migration", "staging", "bake", "production", "upgrade"],
    "confidential": ["security", "pii", "encryption", "secret", "data"],
    "compute": ["infra", "infrastructure", "enterprise", "cluster", "aws", "budget", "cost", "provisioning"],
    "budget": ["compute", "cost", "expense", "lakhs", "spend", "quarter", "provisioning", "finance"],
    "cost": ["budget", "compute", "expense", "lakhs", "enterprise", "finance"],
    "lakhs": ["budget", "cost", "compute", "enterprise", "inr"],
    "aws": ["cloud", "compute", "infra", "production", "cluster"],
    "api": ["apis", "blocked", "unsupported", "deprecated", "third", "party", "legacy", "sdk", "unapproved"],
    "apis": ["api", "blocked", "unsupported", "deprecated", "third", "party", "legacy", "sdk"],
    "blocked": ["unsupported", "api", "apis", "deprecated", "prohibited", "unapproved", "third"],
    "unsupported": ["blocked", "api", "apis", "deprecated", "unapproved", "legacy", "prohibited"],
    "legacy": ["deprecated", "unsupported", "blocked", "api", "v1", "payment"],
    "sdk": ["api", "apis", "third", "party", "unapproved", "unsupported", "blocked"],
    "deprecated": ["blocked", "unsupported", "legacy", "api", "prohibited"],
}


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError(f"Embedding dimension mismatch: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def deterministic_semantic_embedding(text: str, dim: int = 1024) -> List[float]:
    """Generate a reproducible unit-normalized semantic embedding offline."""
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        vec[0] = 1.0
        return vec

    weighted_terms: List[tuple[str, float]] = []
    for tok in tokens:
        weighted_terms.append((tok, 1.0))
        for syn in _CONCEPT_EXPANSIONS.get(tok, []):
            weighted_terms.append((syn, 0.55))

    for i in range(len(tokens) - 1):
        weighted_terms.append((f"{tokens[i]}_{tokens[i + 1]}", 0.7))

    for term, weight in weighted_terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        h1 = int.from_bytes(digest[:4], "big")
        h2 = int.from_bytes(digest[4:], "big")
        idx1 = h1 % dim
        idx2 = h2 % dim
        sign1 = 1.0 if (h1 & 1) == 0 else -1.0
        sign2 = 1.0 if (h2 & 1) == 0 else -1.0
        vec[idx1] += sign1 * weight
        vec[idx2] += sign2 * (weight * 0.5)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        vec[0] = 1.0
        return vec
    return [round(v / norm, 6) for v in vec]


def _is_real_key(val: str) -> bool:
    return bool(val and "placeholder" not in val.lower())


def get_embedding(text: str, dim: Optional[int] = None) -> List[float]:
    """Embed text using configured NVIDIA NIM API or deterministic offline fallback."""
    settings = get_settings()
    target_dim = dim or settings.embedding_dim

    if _is_real_key(settings.nvidia_api_key):
        url = f"{settings.nvidia_base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {settings.nvidia_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.embedding_model,
            "input": [text],
            "encoding_format": "float",
            "input_type": "query",
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                emb = resp.json()["data"][0]["embedding"]
                if len(emb) != target_dim:
                    raise ValueError(
                        f"Embedding provider returned {len(emb)} dims, expected {target_dim}"
                    )
                logger.info(
                    "[EMBED] provider=nvidia model=%s dim=%d",
                    settings.embedding_model, len(emb),
                )
                return emb
        except Exception as exc:
            if not settings.demo_mode:
                logger.warning(
                    "Live NVIDIA embedding call failed (%s); falling back to deterministic 1024-dim embedder.",
                    exc,
                )
            else:
                logger.warning(
                    "Live embedding call failed (%s); falling back to deterministic embedding in DEMO_MODE.",
                    exc,
                )

    return deterministic_semantic_embedding(text, dim=target_dim)
