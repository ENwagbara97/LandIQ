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
        # OCR/Vision: llama-3.2-11b confirmed working on NIM at 1.9s (2026-08-14 live test).
        # nemotron-nano-12b-v2-vl and llama-3.2-90b are unresponsive (3+ min timeout, marked DEAD).
        # Fast-path: Gemini Direct is tried FIRST for vision/OCR inside ai_complete().
        # NIM llama-3.2-11b is Tier-1 backup; OpenRouter gemini-2.5-flash is Tier-2.
        "ocr":              "meta/llama-3.2-11b-vision-instruct",  # NIM: confirmed 1.9s
        "ocr_fallback":     "meta/llama-3.2-11b-vision-instruct",  # same — skip dead models
        "ocr_openrouter":   "google/gemini-2.5-flash",              # OR: confirmed 1.2s
        "vision":           "meta/llama-3.2-11b-vision-instruct",  # NIM: confirmed 1.9s
        "vision_fallback":  "meta/llama-3.2-11b-vision-instruct",  # same — skip dead 90B
        "vision_openrouter": "google/gemini-2.5-flash",             # OR: confirmed 1.2s
        # Reasoning: both NIM models confirmed working (1.0s and 5.5s respectively)
        "reasoning":            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",  # 1.0s OK
        "reasoning_fallback":   "nvidia/llama-3.3-nemotron-super-49b-v1",         # 5.5s OK
        "reasoning_openrouter": "google/gemini-2.5-pro",
        # Report: llama-3.3-70b works but is slow (36s). OR gemini-2.5-flash wins (1.2s).
        "report":            "meta/llama-3.3-70b-instruct",  # NIM fallback (slow)
        "report_openrouter": "google/gemini-2.5-flash",       # OR primary (fast)
        "fast":              "meta/llama-3.2-11b-vision-instruct",  # NIM: confirmed 1.9s
        "fast_openrouter":   "google/gemini-2.5-flash",
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
        max_retries=0,
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
        max_retries=0,
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
    default_model = os.getenv("LLM_DEFAULT", "google/gemini-2.5-flash")
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
        # Fast path for Vision/OCR: inject image into Gemini Direct payload
        # (pass raw image_b64 — Gemini Direct builds its own payload independently)
        gemini_fast = _try_gemini_direct([], max_tokens, temperature, image_b64=image_b64,
                                         messages_raw=messages)
        if gemini_fast is not None:
            return gemini_fast

    # ── TIER 1: NVIDIA NIM ───────────────────────────────────────────────────
    client = _nvidia_client()
    if client:
        # Per-task NIM timeouts (tuned from 2026-08-14 live test results):
        #   ocr/vision: 15s  — llama-3.2-11b confirmed 1.9s; dead models already removed
        #   reasoning:  20s  — nemotron-reasoning confirmed 1.0s; super-49b confirmed 5.5s
        #   report:     42s  — llama-3.3-70b confirmed 36s (slow but works)
        #   fast/other: 15s  — llama-3.2-11b confirmed 1.9s
        if task in ("ocr", "vision"):
            nv_timeout = 15
        elif task == "reasoning":
            nv_timeout = 20
        elif task == "report":
            nv_timeout = 42
        else:
            nv_timeout = max(15, timeout)
        primary_model  = MODEL_ROUTING.get(task, "")
        fallback_model = MODEL_ROUTING.get(f"{task}_fallback", "")
        # Deduplicate — if primary == fallback (e.g. ocr), only call once
        nim_models = list(dict.fromkeys(filter(None, [primary_model, fallback_model])))
        for model in nim_models:
            result = _try_complete(client, model, messages,
                                   max_tokens, temperature, nv_timeout,
                                   "nvidia", task)
            if result is not None:
                return result

    # ── TIER 2: OPENROUTER ───────────────────────────────────────────────────
    client = _openrouter_client()
    if client:
        or_model = MODEL_ROUTING.get(f"{task}_openrouter", "")
        if or_model:
            # Clip max_tokens to 1500 for OpenRouter to prevent 402 Payment Required on low credit accounts
            or_max_tokens = min(max_tokens, 1500) if max_tokens else 1024
            result = _try_complete(client, or_model, messages,
                                   or_max_tokens, temperature, timeout,
                                   "openrouter", task)
            if result is not None:
                return result

    # ── TIER 3: KAGGLE PROXY (Text tasks only) ─────────────────────────────
    if not image_b64:
        client, kaggle_model = _kaggle_client()
        if client and kaggle_model:
            result = _try_complete(client, kaggle_model, messages,
                                   max_tokens, temperature, timeout,
                                   "kaggle", task)
            if result is not None:
                return result

    # ── TIER 3.5: GEMINI DIRECT (Fallback for text tasks) ─────────────────
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


def _try_gemini_direct(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    image_b64: str | None = None,
    messages_raw: list[dict] | None = None,
) -> str | None:
    """Tier 3.5: Gemini Direct fallback using Google AI Studio GEMINI_API_KEY.
    Uses gemini-3.5-flash (verified working via key starting with AQ.).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"')
    if not api_key:
        return None
    import requests

    # Use messages_raw if provided (preserves original un-injected messages)
    src = messages_raw if messages_raw else messages
    system = ""
    prompt = ""
    for m in src:
        if m.get("role") == "system":
            c = m.get("content", "")
            system = c if isinstance(c, str) else ""
        elif m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, str):
                prompt = c
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        prompt = part.get("text", "")

    # Model priority — gemini-3-flash-preview is fastest (1.2s), gemini-3.5-flash is secondary
    gemini_models = [
        ("gemini-3-flash-preview", 20),   # primary: avg 1.2s, very reliable
        ("gemini-3.5-flash",       40),   # fallback: occasionally slow but available
        ("gemini-flash-latest",    30),   # alias fallback
    ]
    parts_base = []
    if system:
        parts_base.append({"text": f"System Instruction:\n{system}\n\nUser Prompt:\n{prompt}"})
    else:
        parts_base.append({"text": prompt or "Process this request."})
    if image_b64:
        parts_base.append({"inlineData": {"mimeType": "image/png", "data": image_b64}})

    for model, model_timeout in gemini_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        # Gemini thinking models: set thinkingBudget: 0 to eliminate token consumption on thought loops
        # and ensure 100% of token budget (8192) is dedicated to output text (preventing JSON truncation).
        gemini_max_tokens = max(max_tokens, 8192)
        payload = {
            "contents": [{"parts": list(parts_base)}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": gemini_max_tokens,
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        try:
            resp = requests.post(url, json=payload, timeout=model_timeout)
            if resp.ok:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    cand_parts = candidates[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "") for p in cand_parts if "text" in p]
                    if text_parts:
                        text = "".join(text_parts).strip()
                        logger.info(f"[ai_client] Gemini Direct ({model}) call succeeded")
                        return text
            else:
                logger.warning(f"[ai_client] Gemini Direct ({model}) HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            logger.warning(f"[ai_client] Gemini Direct ({model}) failed: {exc}, trying next model")
    return None


def _try_ollama(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    task: str,
) -> str | None:
    """Tier 4: Ollama local fallback. Returns text or None."""
    # Fast check: if Ollama isn't explicitly enabled or running, bypass instantly
    if not os.getenv("OLLAMA_ENABLED", "").lower() in ("true", "1"):
        return None
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
