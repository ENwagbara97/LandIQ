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

from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger("landiq.ai_client")

# =============================================================================
# TASK → MODEL ROUTING
# Override any value in .env to swap models without code changes.
# =============================================================================
def _get_model(key: str, default: str = "") -> str:
    """Read latest model string from environment or defaults."""
    defaults = {
        # OCR/Vision: nvidia/nemotron-nano-12b-v2-vl is the correct NIM vision model
        "ocr": "nvidia/nemotron-nano-12b-v2-vl",
        "ocr_fallback": "meta/llama-3.2-90b-vision-instruct",
        "ocr_openrouter": "google/gemini-2.5-flash",
        "vision": "meta/llama-3.2-90b-vision-instruct",
        "vision_fallback": "meta/llama-3.2-11b-vision-instruct",
        "vision_openrouter": "meta-llama/llama-3.2-11b-vision-instruct:free",
        # Reasoning: nvidia/llama-3.3-nemotron-super-49b-v1 is the correct NIM name
        "reasoning": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "reasoning_fallback": "nvidia/llama-3.1-nemotron-70b-instruct",
        "reasoning_openrouter": "nvidia/llama-3.3-nemotron-super-49b-v1:free",
        # Report: these are correct NIM model IDs
        "report": "meta/llama-3.3-70b-instruct",
        "report_openrouter": "meta-llama/llama-3.3-70b-instruct",
        "fast": "meta/llama-3.2-11b-vision-instruct",
        "fast_openrouter": "meta-llama/llama-3.2-11b-vision-instruct:free",
    }
    env_name = f"LLM_{key.upper()}"
    return os.getenv(env_name, defaults.get(key, default))

MODEL_ROUTING = {k: _get_model(k) for k in [
    "ocr", "ocr_fallback", "ocr_openrouter",
    "vision", "vision_fallback", "vision_openrouter",
    "reasoning", "reasoning_fallback", "reasoning_openrouter",
    "report", "report_openrouter", "fast", "fast_openrouter"
]}

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
    Uses full key from MODEL_PROXY_API_KEY.
    """
    from openai import OpenAI
    proxy_url = os.getenv("MODEL_PROXY_URL", "")
    proxy_key = os.getenv("MODEL_PROXY_API_KEY", "")
    if not proxy_url or not proxy_key:
        return None, None
    client = OpenAI(
        api_key=proxy_key,
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

    # ── TIER 3.5: GEMINI DIRECT (Google AI Studio Key) ─────────────────────
    gemini_result = _try_gemini_direct(messages, max_tokens, temperature, image_b64=image_b64)
    if gemini_result is not None:
        return gemini_result

    # ── TIER 4: OLLAMA LOCAL ─────────────────────────────────────────────────
    ollama_result = _try_ollama(messages, max_tokens, temperature, task)
    if ollama_result is not None:
        return ollama_result

    logger.error(f"[ai_client] All tiers failed for task='{task}'")
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


def _try_gemini_direct(messages: list[dict], max_tokens: int, temperature: float, image_b64: str | None = None) -> str | None:
    """Tier 3.5: Gemini Direct fallback using Google AI Studio GEMINI_API_KEY."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    import requests
    system = ""
    prompt = ""
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "")
        elif m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, str):
                prompt = c
            elif isinstance(c, list):
                for part in c:
                    if part.get("type") == "text":
                        prompt = part.get("text", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    parts = []
    if system:
        parts.append({"text": f"System Instruction:\n{system}\n\nUser Prompt:\n{prompt}"})
    else:
        parts.append({"text": prompt or "Process this request."})
    if image_b64:
        parts.append({"inlineData": {"mimeType": "image/png", "data": image_b64}})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
    }
    try:
        resp = requests.post(url, json=payload, timeout=25)
        if resp.ok:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                cand_parts = candidates[0].get("content", {}).get("parts", [])
                if cand_parts and "text" in cand_parts[0]:
                    text = cand_parts[0]["text"].strip()
                    logger.info("[ai_client] Gemini Direct call succeeded")
                    return text
    except Exception as exc:
        logger.warning(f"[ai_client] Gemini Direct call failed: {exc}")
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
