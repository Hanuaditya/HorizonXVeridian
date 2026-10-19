"""
agent/llm_client.py — Veridian WorkOS Nvidia NIM LLM Client
=============================================================
Centralised, reusable wrapper around the OpenAI-compatible Nvidia NIM API.
All agent nodes import from this module — never instantiate OpenAI directly.

Three public functions:
  chat_completion()   — free-form chat, returns assistant message string
  structured_output() — tool-calling forced JSON, validated against Pydantic
  get_embedding()     — 1024-dim Nvidia embedding vector

All calls have automatic exponential-backoff retry (max 3 attempts).
Credentials are always read from environment variables — never hardcoded.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Type, TypeVar

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, ValidationError

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LLM_MODEL = "meta/llama-3.1-70b-instruct"       # Upgraded for perfect tool calling
EMBEDDING_MODEL = "nvidia/nv-embedqa-e5-v5"      # 1024-dim Nvidia embeddings
EMBEDDING_DIMENSIONS = 1024

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2   # Retry delays: 2s, 4s, 8s

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Client factory (lazy, reads env on every call so tests can monkeypatch)
# ---------------------------------------------------------------------------

from langsmith.wrappers import wrap_openai

def _get_client() -> OpenAI:
    """
    Build an OpenAI client pointed at Nvidia NIM.
    Reads NVIDIA_API_KEY and NVIDIA_BASE_URL from environment.
    Raises EnvironmentError early rather than getting a cryptic 401.
    """
    api_key = os.getenv("NVIDIA_API_KEY")
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

    if not api_key:
        raise EnvironmentError(
            "NVIDIA_API_KEY is not set. Add it to your .env file."
        )

    # Wrap the raw OpenAI client so LangSmith captures the LLM calls
    return wrap_openai(OpenAI(api_key=api_key, base_url=base_url))



# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _with_retry(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) with exponential-backoff retry.

    Retryable errors:
      - RateLimitError       (429 — back off and retry)
      - APIConnectionError   (network blip)
      - APIStatusError 5xx   (NIM server error)

    Non-retryable errors (4xx except 429) are re-raised immediately.

    Delays: 2 s → 4 s → 8 s (doubles each attempt).
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)

        except RateLimitError as exc:
            last_exc = exc
            wait = BACKOFF_BASE_SECONDS ** attempt
            logger.warning(
                "Rate limited by Nvidia NIM (attempt %d/%d). "
                "Retrying in %ds…",
                attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)

        except APIConnectionError as exc:
            last_exc = exc
            wait = BACKOFF_BASE_SECONDS ** attempt
            logger.warning(
                "Connection error (attempt %d/%d). Retrying in %ds…",
                attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)

        except APIStatusError as exc:
            if exc.status_code >= 500:
                # Server-side error — worth retrying
                last_exc = exc
                wait = BACKOFF_BASE_SECONDS ** attempt
                logger.warning(
                    "Nvidia NIM server error %d (attempt %d/%d). "
                    "Retrying in %ds…",
                    exc.status_code, attempt, MAX_RETRIES, wait,
                )
                time.sleep(wait)
            else:
                # Client-side error (401, 403, 400) — do not retry
                logger.error(
                    "Non-retryable API error %d: %s",
                    exc.status_code, exc.message,
                )
                raise

    logger.error(
        "All %d retry attempts exhausted. Last error: %s",
        MAX_RETRIES, last_exc,
    )
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public API — 1. chat_completion
# ---------------------------------------------------------------------------

def chat_completion(
    messages: List[Dict[str, str]],
    response_format: Optional[Dict[str, str]] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Free-form chat completion via Nvidia NIM.

    Args:
        messages:        OpenAI-format message list,
                         e.g. [{"role": "user", "content": "..."}]
        response_format: Optional dict, e.g. {"type": "json_object"}.
                         Pass this only when you can live with soft-JSON
                         (prefer structured_output() for strict schemas).
        temperature:     Sampling temperature. 0.2 for factual / agentic tasks.
        max_tokens:      Maximum tokens in the response.

    Returns:
        The assistant's reply as a plain string.

    Raises:
        EnvironmentError: NVIDIA_API_KEY not set.
        openai.APIError: After all retries are exhausted.
    """
    client = _get_client()

    kwargs: Dict[str, Any] = dict(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format

    def _call():
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    result: str = _with_retry(_call)
    logger.debug("chat_completion → %d chars", len(result))
    return result


# ---------------------------------------------------------------------------
# Public API — 2. structured_output  (THE CRITICAL FUNCTION)
# ---------------------------------------------------------------------------

def structured_output(
    messages: List[Dict[str, str]],
    pydantic_model: Type[T],
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> T:
    """
    Force the LLM to return exactly one valid instance of `pydantic_model`
    using Nvidia NIM's tool-calling API.

    How it works:
      1. Convert the Pydantic model to a JSON Schema function definition.
      2. Submit it as a *single* tool and set tool_choice to force the LLM
         to call it (no free-text fallback possible).
      3. Extract the tool_call arguments JSON string from the response.
      4. Validate the JSON through the Pydantic model — raises ValueError
         on any schema mismatch so the caller always gets clean data or
         an explicit exception (never partial / hallucinated data).

    Args:
        messages:       OpenAI-format message list.
        pydantic_model: The Pydantic BaseModel class describing
                        the exact JSON structure required.
        temperature:    Set to 0.0 for deterministic tool calls.
        max_tokens:     Max tokens for the response.

    Returns:
        A validated instance of pydantic_model.

    Raises:
        EnvironmentError: NVIDIA_API_KEY not set.
        ValueError:    JSON from LLM fails Pydantic validation.
        RuntimeError:  LLM did not call the tool (should never happen
                       with tool_choice forced, but defensive check).
        openai.APIError: After all retries are exhausted.
    """
    client = _get_client()
    model_name = pydantic_model.__name__

    # ── Step 1: Build the tool definition from the Pydantic schema ──────
    json_schema = pydantic_model.model_json_schema()

    # Remove $defs — inline them so Nvidia NIM doesn't choke on $ref
    # (NIM tool schemas must be fully flattened)
    json_schema = _flatten_schema(json_schema)

    tool_definition = {
        "type": "function",
        "function": {
            "name": model_name,
            "description": (
                f"Extract structured data matching the {model_name} schema. "
                "Fill every required field. Use null for truly unknown optionals."
            ),
            "parameters": json_schema,
        },
    }

    # ── Step 2: Force tool call ──────────────────────────────────────────
    def _call():
        return client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=[tool_definition],
            tool_choice={"type": "function", "function": {"name": model_name}},
            temperature=temperature,
            max_tokens=max_tokens,
        )

    response = _with_retry(_call)

    # ── Step 3: Extract tool_call arguments ─────────────────────────────
    choice = response.choices[0]
    tool_calls = getattr(choice.message, "tool_calls", None)

    if not tool_calls:
        # Defensive: should never happen when tool_choice is forced
        raw_content = choice.message.content or ""
        logger.error(
            "structured_output: LLM did not invoke the tool.\n"
            "Raw content: %s", raw_content[:500]
        )
        raise RuntimeError(
            f"LLM did not call the '{model_name}' tool. "
            "This usually means the model context was too long or "
            "the schema was rejected. Raw content: " + raw_content[:200]
        )

    arguments_str: str = tool_calls[0].function.arguments
    logger.debug(
        "structured_output raw args (%d chars): %s",
        len(arguments_str), arguments_str[:300],
    )

    # ── Step 4: Parse + validate through Pydantic ──────────────────────
    try:
        arguments_dict = json.loads(arguments_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned invalid JSON for '{model_name}': {exc}\n"
            f"Raw: {arguments_str[:400]}"
        ) from exc

    try:
        validated = pydantic_model.model_validate(arguments_dict)
    except ValidationError as exc:
        raise ValueError(
            f"LLM output failed Pydantic validation for '{model_name}':\n"
            f"{exc}\n\nRaw arguments: {arguments_str[:400]}"
        ) from exc

    logger.info("structured_output → valid %s instance", model_name)
    return validated


# ---------------------------------------------------------------------------
# Public API — 3. get_embedding
# ---------------------------------------------------------------------------

def get_embedding(text: str) -> List[float]:
    """
    Generate a 1024-dimensional Nvidia NV-EmbedQA-E5-v5 embedding.

    Used by:
      - finance_checker_node  (semantic match vs. budget categories)
      - security_checker_node (RAG similarity vs. policy chunks)

    Args:
        text: The text to embed. Will be truncated by the model if too long.

    Returns:
        List of 1024 floats (cosine-normalised, ready for pgvector <=> queries).

    Raises:
        EnvironmentError: NVIDIA_API_KEY not set.
        ValueError:       Returned vector has wrong dimension (sanity check).
        openai.APIError:  After all retries are exhausted.
    """
    client = _get_client()

    def _call():
        return client.embeddings.create(
            input=[text],
            model=EMBEDDING_MODEL,
            encoding_format="float",
            extra_body={
                "input_type": "query",
                "truncate": "END",   # Silently truncate rather than error
            },
        )

    response = _with_retry(_call)
    vector: List[float] = response.data[0].embedding

    # Sanity-check dimension so bad vectors never reach pgvector
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS}-dim embedding, "
            f"got {len(vector)} dims from {EMBEDDING_MODEL}. "
            "Check NVIDIA_BASE_URL is pointing at the correct NIM endpoint."
        )

    logger.debug("get_embedding → %d dims for text: '%s…'", len(vector), text[:60])
    return vector


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flatten_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively resolve $ref/$defs in a JSON Schema dict so the
    resulting schema has no references — required for NIM tool definitions.

    Most Pydantic V2 schemas use $defs for nested models. NIM's tool
    calling backend doesn't follow $ref, so we inline them here.
    """
    defs = schema.pop("$defs", {})
    if not defs:
        return schema

    schema_str = json.dumps(schema)

    # Simple single-pass inline: replace every "$ref": "#/$defs/Foo"
    # with the actual definition. Works for 1-level-deep nesting which
    # covers all schemas in this project (Task, FirewallResult, etc.)
    for def_name, def_schema in defs.items():
        ref_token = json.dumps({"$ref": f"#/$defs/{def_name}"})
        replacement = json.dumps(def_schema)
        # ref_token includes surrounding {}, replacement does too —
        # we need to splice cleanly inside an object property value
        schema_str = schema_str.replace(
            f'"$ref": "#/$defs/{def_name}"',
            *[f'"{k}": {json.dumps(v)}' for k, v in def_schema.items()][:1]
            or ['"type": "object"'],
        )

    # A more robust approach: full recursive resolve
    result = json.loads(schema_str)
    return _resolve_refs(result, defs)


def _resolve_refs(
    obj: Any, defs: Dict[str, Any], depth: int = 0
) -> Any:
    """
    Recursively walk `obj` and replace any {"$ref": "#/$defs/Foo"} with
    the inlined definition from `defs`. Handles nested models up to depth 5.
    """
    if depth > 5:          # Guard against circular refs
        return obj

    if isinstance(obj, dict):
        if "$ref" in obj:
            ref_path = obj["$ref"]           # e.g. "#/$defs/FirewallResult"
            def_name = ref_path.split("/")[-1]
            if def_name in defs:
                return _resolve_refs(defs[def_name], defs, depth + 1)
            return obj
        return {k: _resolve_refs(v, defs, depth + 1) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_resolve_refs(item, defs, depth + 1) for item in obj]

    return obj


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly: python -m agent.llm_client)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("Veridian LLM Client — Smoke Test")
    print("=" * 60)

    # Test 1: Embedding
    print("\n[1/2] Testing get_embedding('enterprise compute budget')…")
    try:
        vec = get_embedding("enterprise compute budget")
        print(f"      ✅ Vector dim: {len(vec)}  |  first 5 values: {vec[:5]}")
    except Exception as exc:
        print(f"      ❌ {exc}")
        sys.exit(1)

    # Test 2: chat_completion
    print("\n[2/2] Testing chat_completion…")
    try:
        reply = chat_completion([
            {"role": "user", "content": "Reply with exactly three words: test successful complete"}
        ])
        print(f"      ✅ Reply: '{reply.strip()}'")
    except Exception as exc:
        print(f"      ❌ {exc}")
        sys.exit(1)

    print("\n✅ All smoke tests passed. LLM client is ready.\n")
