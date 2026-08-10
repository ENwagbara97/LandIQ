"""
LandIQ — agents/ai_router.py
Agent Task Router for AI Completions

Routes specific agent subtasks to core/ai_client.py with task-specific defaults.

Routing Table:
  SURVEY_OCR          → task="ocr"       (Nemotron OCR v2 / Gemini 2.5 Flash)
  VIA_ANALYSIS        → task="vision"    (Llama 3.2 90B Vision / 11B Vision)
  PLAN_CLASSIFY       → task="reasoning" (Nemotron 3 Super 49B / Ultra 550B)
  METRIC_TRANSLATION  → task="report"    (Llama 3.3 70B Instruct)
  EXECUTIVE_SUMMARY   → task="report"    (Llama 3.3 70B Instruct)
  FAST_CLASSIFY       → task="fast"      (Llama 3.2 11B Vision)

Usage:
  from agents.ai_router import route_completion
  text = route_completion("METRIC_TRANSLATION", messages=[...])
"""
from __future__ import annotations

import logging
from typing import Any
from core.ai_client import (
    ai_complete,
    complete_ocr,
    complete_vision,
    complete_reasoning,
    complete_report,
    complete_fast,
    TaskType,
)

logger = logging.getLogger("landiq.ai_router")

# Map agent task names to ai_client TaskTypes
AGENT_TASK_MAP: dict[str, TaskType] = {
    "SURVEY_OCR":         "ocr",
    "VIA_ANALYSIS":       "vision",
    "PLAN_CLASSIFY":      "reasoning",
    "METRIC_TRANSLATION": "report",
    "EXECUTIVE_SUMMARY":  "report",
    "FAST_CLASSIFY":      "fast",
}


def route_completion(
    agent_task: str,
    messages: list[dict],
    image_b64: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    timeout: int = 30,
) -> str | None:
    """
    Route an agent completion request to core/ai_client.py.

    Args:
        agent_task : One of SURVEY_OCR, VIA_ANALYSIS, PLAN_CLASSIFY,
                     METRIC_TRANSLATION, EXECUTIVE_SUMMARY, FAST_CLASSIFY.
        messages   : OpenAI-format message list [{"role": "user", "content": ...}].
        image_b64  : Optional base64 string for vision/OCR.
        max_tokens : Max tokens to generate.
        temperature: Temperature setting.
        timeout    : Timeout in seconds.

    Returns:
        Generated text string or None if all providers fail.
    """
    task_type: TaskType = AGENT_TASK_MAP.get(agent_task.upper(), "report")
    logger.info(f"[ai_router] Routing agent_task='{agent_task}' → task_type='{task_type}'")

    return ai_complete(
        task=task_type,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        image_b64=image_b64,
    )
