"""
LandIQ — core/ai_client.py
Unified 4-Tier AI Client

Execution order for every task:
  Tier 1: NVIDIA NIM   — fastest, Nemotron / Llama optimised models
  Tier 2: OpenRouter   — broad coverage, unified key, free tier
  Tier 3: Kaggle Proxy — existing wired free backup (Gemini, DeepSeek, GPT-4o, etc.)
  Tier 4: Ollama local — zero-network safety net for local dev

RULES (never violate):
  - LLMs only handle text/vision tasks — never spatial math.
  - This module never raises. Callers always get str | None.
  - All providers use OpenAI-compatible SDK (same request format).
  - Kaggle proxy uses its own auth header format — handled here.
  - Add to .env: NVIDIA_API_KEY, OPENROUTER_API_KEY (Kaggle already wired).

Usage:
  from core.ai_client import ai_complete, complete_ocr, complete_vision, complete_report
  result = complete_report(messages=[{"role": "user", "content": "..."}])
"""
from __future__ import annotations

import logging
import os
import time
from typing import Literal

logger = logging.getLogger("landiq.ai_client")

# =============================================================================
# TASK → MODEL ROUTING
# Override any value in .env to swap models without code changes.
# =============================================================================
MODEL_ROUTING: dict[str, str] = {
    # OCR: survey plan image extraction
    "ocr":                os.getenv("LLM_OCR",               "nvidia/nemotron-ocr-v2"),
    "ocr_fallback":       os.getenv("LLM_OCR_FALLBACK",      "nvidia/nemotron-nano-12b-v2-vl"),
    "ocr_openrouter":     os.getenv("LLM_OCR_OPENROUTER",    "google/gemini-2.5-flash"),
    # Vision: VIA satellite analysis
    "vision":             os.getenv("LLM_VISION",            "meta/llama-3.2-90b-vision-instruct"),
    "vision_fallback":    os.getenv("LLM_VISION_FALLBACK",   "meta/llama-3.2-11b-vision-instruct"),
    "vision_openrouter":  os.getenv("LLM_VISION_OPENROUTER", "meta-llama/llama-3.2-11b-vision-instruct:free"),
    # Reasoning: expert summary, plan classification
    "reasoning":          os.getenv("LLM_REASONING",         "nvidia/nemotron-3-super-49b-a5b"),
    "reasoning_fallback": os.getenv("LLM_REASONING_FALLBACK","nvidia/nemotron-3-super-49b-a5b"),
    "reasoning_openrouter": os.getenv("LLM_REASONING_OPENROUTER", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    # Report: metric translation + executive summary
    "report":             os.getenv("LLM_REPORT",            "meta/llama-3.3-70b-instruct"),
    "report_openrouter":  os.getenv("LLM_REPORT_OPENROUTER", "meta-llama/llama-3.3-70b-instruct:free"),
    # Fast: quick classification / routing tasks
    "fast":               os.getenv("LLM_FAST",              "meta/llama-3.2-11b-vision-instruct"),
    "fast_openrouter":    os.getenv("LLM_FAST_OPENROUTER",   "meta-llama/llama-3.2-11b-vision-instruct:free"),
}

TaskType = Literal["ocr", "vision", "reasoning", "report", "fast"]


# =============================================================================
# PROVIDER CLIENT FACTORIES
# =============================================================================

def _nvidia_client():
    """NVIDIA NIM — OpenAI-compatible API."""
    from openai import OpenAI
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    )


def _openrouter_client():
    """OpenRouter — broad model coverage, unified key."""
    from openai import OpenAI
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        default_headers={
            "HTTP-Referer": "https://landiq.app",
            "X-Title": "LandIQ",
        },
    )


def _kaggle_client():
    """
    Kaggle Model Proxy — existing free backup already wired in .env.
    Uses a bearer token from MODEL_PROXY_API_KEY.
    """
    from openai import OpenAI
    proxy_url = os.getenv("MODEL_PROXY_URL", "")
    proxy_key  = os.getenv("MODEL_PROXY_API_KEY", "")
    if not proxy_url or not proxy_key:
        return None, None
    # Kaggle proxy uses a Kaggle-formatted key — strip non-standard prefix if present
    bearer = proxy_key.split(":")[-1] if ":" in proxy_key else proxy_key
    client = OpenAI(
        api_key=bearer,
        base_url=proxy_url,
    )
    default_model = os.getenv("LLM_DEFAULT", "google/gemini-3-flash-preview")
    return client, default_model


# =============================================================================
# CORE COMPLETION FUNCTION
# =============================================================================

def ai_complete(
    task: TaskType,
    messages: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.2,
    timeout: int = 30,
    image_b64: str | None = None,
) -> str | None:
    """
    Unified AI completion with 4-tier failover.
    Returns the response text string, or None if all providers fail.
    Never raises — callers must handle None gracefully.

    Args:
        task       : Task type — determines model routing.
        messages   : OpenAI-format message list.
        max_tokens : Maximum output tokens.
        temperature: Sampling temperature (0.0–1.0).
        timeout    : Per-provider HTTP timeout in seconds.
        image_b64  : Optional base64 image string for vision/OCR tasks.
    """
    # Build the message list (inject image into last user message if provided)
    if image_b64 and task in ("ocr", "vision"):
        messages = _inject_image(messages, image_b64)

    # ── TIER 1: NVIDIA NIM ───────────────────────────────────────────────────
    client = _nvidia_client()
    if client:
        primary_model   = MODEL_ROUTING.get(task, "")
        fallback_model  = MODEL_ROUTING.get(f"{task}_fallback", "")
        for model in filter(None, [primary_model, fallback_model]):
            result = _try_complete(client, model, messages,
                                   max_tokens, temperature, timeout,
                                   "nvidia", task)
            if result is not None:
                return result

    # ── TIER 2: OPENROUTER ───────────────────────────────────────────────────
    client = _openrouter_client()
    if client:
        or_model = MODEL_ROUTING.get(f"{task}_openrouter", "")
        if or_model:
            result = _try_complete(client, or_model, messages,
                                   max_tokens, temperature, timeout,
                                   "openrouter", task)
            if result is not None:
                return result

    # ── TIER 3: KAGGLE PROXY ─────────────────────────────────────────────────
    client, kaggle_model = _kaggle_client()
    if client and kaggle_model:
        result = _try_complete(client, kaggle_model, messages,
                               max_tokens, temperature, timeout,
                               "kaggle", task)
        if result is not None:
            return result

    # ── TIER 4: OLLAMA LOCAL ─────────────────────────────────────────────────
    ollama_result = _try_ollama(messages, max_tokens, temperature, task)
    if ollama_result is not None:
        return ollama_result

    logger.error(f"[ai_client] All 4 tiers failed for task='{task}'")
    return None


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _try_complete(
    client,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: int,
    provider: str,
    task: str,
) -> str | None:
    """Attempt one completion. Returns text or None on any error."""
    try:
        start = time.monotonic()
        logger.info(f"[ai_client] {task} → {provider}/{model}")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        elapsed = time.monotonic() - start
        text = response.choices[0].message.content or ""
        logger.info(
            f"[ai_client] {task} ✓ via {provider}/{model} "
            f"in {elapsed:.1f}s ({len(text)} chars)"
        )
        return text.strip() or None
    except Exception as exc:
        logger.warning(f"[ai_client] {task} ✗ via {provider}/{model}: {exc}")
        return None


def _try_ollama(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    task: str,
) -> str | None:
    """Tier 4: Ollama local fallback. Returns text or None."""
    try:
        import ollama  # type: ignore
        model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
        logger.info(f"[ai_client] {task} → ollama/{model}")
        response = ollama.chat(
            model=model,
            messages=messages,
            options={"num_predict": max_tokens, "temperature": temperature},
        )
        text = response.get("message", {}).get("content", "")
        if text.strip():
            logger.info(f"[ai_client] {task} ✓ via ollama/{model}")
            return text.strip()
        return None
    except ImportError:
        logger.debug("[ai_client] Ollama not installed — tier 4 skipped")
        return None
    except Exception as exc:
        logger.warning(f"[ai_client] Ollama failed: {exc}")
        return None


def _inject_image(messages: list[dict], image_b64: str) -> list[dict]:
    """
    Converts the last user message content into a multimodal content list
    with the image prepended (required by vision models).
    """
    if not messages:
        return messages
    msgs = list(messages)
    last = dict(msgs[-1])
    text_content = last.get("content", "Analyse this image.")
    if isinstance(text_content, str):
        last["content"] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
            {"type": "text", "text": text_content},
        ]
    msgs[-1] = last
    return msgs


# =============================================================================
# CONVENIENCE HELPERS (used by migrated agents)
# =============================================================================

def complete_ocr(messages: list[dict], image_b64: str, **kw) -> str | None:
    """OCR-specific completion — always vision-capable model."""
    return ai_complete("ocr", messages, image_b64=image_b64,
                       max_tokens=kw.get("max_tokens", 4096),
                       timeout=kw.get("timeout", 45))


def complete_vision(messages: list[dict], image_b64: str, **kw) -> str | None:
    """VIA satellite image analysis."""
    return ai_complete("vision", messages, image_b64=image_b64,
                       max_tokens=kw.get("max_tokens", 1024),
                       timeout=kw.get("timeout", 30))


def complete_reasoning(messages: list[dict], **kw) -> str | None:
    """Complex reasoning — expert summary, plan classification."""
    return ai_complete("reasoning", messages,
                       max_tokens=kw.get("max_tokens", 2000),
                       timeout=kw.get("timeout", 40))


def complete_report(messages: list[dict], **kw) -> str | None:
    """Standard report narrative — metric translation + executive summary."""
    return ai_complete("report", messages,
                       max_tokens=kw.get("max_tokens", 600),
                       temperature=kw.get("temperature", 0.3),
                       timeout=kw.get("timeout", 20))


def complete_fast(messages: list[dict], **kw) -> str | None:
    """Lightweight fast classification or routing task."""
    return ai_complete("fast", messages,
                       max_tokens=kw.get("max_tokens", 500),
                       timeout=kw.get("timeout", 15))
