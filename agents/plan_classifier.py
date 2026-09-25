"""
LandIQ — agents/plan_classifier.py
Plan Type Classification Engine (Chapter 1 — Masterclass Prompt v1.0)

Deterministic zero-LLM classifier that reads OCR text and assigns one of
five plan types before any extraction attempt.

TYPE_A — Simple parcel boundary         (existing pipeline, unchanged)
TYPE_B — Composite subdivision plan     (multiple lots, shared boundaries)
TYPE_C — Engineering / topographic      (contours + building footprints)
TYPE_D — Topographic survey only        (contours, no layout)
TYPE_E — Title deed / registry doc      (reject as boundary source)

All decisions are based on text signal detection — no ML, no network calls.
Confidence below FALLBACK_THRESHOLD routes to Gemini Vision classification.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from core.schemas import PlanType

logger = logging.getLogger("landiq.plan_classifier")

# ── Confidence threshold below which Gemini fallback is triggered ─────────────
FALLBACK_THRESHOLD = 0.70


# =============================================================================
# SIGNAL DETECTION HELPERS
# =============================================================================

# Engineering / topographic keywords (Rule 0.4 + Chapter 1.2 SIGNAL 6)
_ENGINEERING_KEYWORDS = re.compile(
    r"polytechnic|university|college|school|hospital|clinic|church|mosque|"
    r"estate\s+layout|site\s+plan|topographic|topo\s+survey|engineering\s+survey|"
    r"contour|elevation|benchmark|b\.m\.|b\.m|amsl|above\s+mean\s+sea|"
    r"building\s+footprint|structure|admin\s+block|laboratory|auditorium",
    re.IGNORECASE,
)

# Title deed / C of O keywords — signals TYPE_E
_TITLE_DEED_KEYWORDS = re.compile(
    r"certificate\s+of\s+occupancy|c\s*of\s*o\b|deed\s+of\s+assignment|"
    r"deed\s+of\s+conveyance|power\s+of\s+attorney|governor.*consent|"
    r"right\s+of\s+occupancy|statutory\s+right|leasehold|freehold\s+title",
    re.IGNORECASE,
)

# Lot number patterns: "Lot 1", "LOT 2", "PLOT 163", bare integers inside text
_LOT_NUMBER_PATTERN = re.compile(
    r"\b(?:lot|plot|parcel)\s*(\d{1,4})\b",
    re.IGNORECASE,
)
_BARE_LOT_NUMBER = re.compile(r"(?<!\d)(\d{1,3})(?!\d)(?!\s*m)")

# Area statements: "1664 m²", "606 sqm", "0.166 ha", "424.846 SQ. METRES"
_AREA_PATTERN = re.compile(
    r"\d[\d,.]*\s*(?:m[²2]|sqm|sq\.?\s*m(?:etres?|eters?)?|hectares?|\bha\b)",
    re.IGNORECASE,
)

# Contour label: standalone integers adjacent to "m" or between 0–200 range
# In text from topo plans: "44", "46", "48" appear as standalone labels
_CONTOUR_LABEL = re.compile(r"\b(?:contour|elevation|rl|reduced\s+level)\b", re.IGNORECASE)


@dataclass
class ClassifierResult:
    plan_type: PlanType
    confidence: float
    signals: list[str] = field(default_factory=list)
    needs_vision_fallback: bool = False


# =============================================================================
# MAIN CLASSIFIER
# =============================================================================

def classify_plan_type(ocr_text: str) -> ClassifierResult:
    """
    Classify the survey document from its OCR text output.
    
    Returns a ClassifierResult with plan_type, confidence (0–1), and
    a list of the signals that fired so the result is auditable.
    
    Chapter 1.2 signal priority:
        contours + buildings → TYPE_C
        contours only        → TYPE_D  
        multiple lots + areas → TYPE_B
        title deed keywords  → TYPE_E
        default              → TYPE_A
    """
    if not ocr_text:
        return ClassifierResult(
            plan_type=PlanType.TYPE_A,
            confidence=0.5,
            signals=["no_text_fallback_to_type_a"],
        )

    signals: list[str] = []
    text = ocr_text

    # ── SIGNAL: Title deed / registry doc ─────────────────────────────────────
    title_deed_matches = _TITLE_DEED_KEYWORDS.findall(text)
    has_title_deed = len(title_deed_matches) > 0
    if has_title_deed:
        signals.append(f"title_deed_keywords:{len(title_deed_matches)}")

    # ── SIGNAL: Engineering / topographic keywords ─────────────────────────────
    eng_matches = _ENGINEERING_KEYWORDS.findall(text)
    has_engineering = len(eng_matches) >= 2  # require at least 2 matches
    if has_engineering:
        signals.append(f"engineering_keywords:{len(eng_matches)}")

    # ── SIGNAL: Contour label word present ────────────────────────────────────
    has_contour_label = bool(_CONTOUR_LABEL.search(text))
    if has_contour_label:
        signals.append("contour_label_present")

    # ── SIGNAL: Multiple area statements ──────────────────────────────────────
    area_matches = _AREA_PATTERN.findall(text)
    has_multiple_areas = len(area_matches) >= 2
    if has_multiple_areas:
        signals.append(f"area_statements:{len(area_matches)}")

    # ── SIGNAL: Multiple named lot numbers ────────────────────────────────────
    named_lots = _LOT_NUMBER_PATTERN.findall(text)
    unique_lots = set(named_lots)
    has_multiple_lots = len(unique_lots) >= 2
    if has_multiple_lots:
        signals.append(f"named_lots:{sorted(unique_lots)}")

    # ── SIGNAL: Legend / symbol table ─────────────────────────────────────────
    has_legend = bool(re.search(r"\blegend\b|\bsymbols?\b|\bkey\b", text, re.IGNORECASE))
    if has_legend:
        signals.append("legend_table_detected")

    # =========================================================================
    # CLASSIFICATION LOGIC (Chapter 1.2 decision tree)
    # =========================================================================

    # TYPE_E — Title deed: reject before any other check
    if has_title_deed and not has_multiple_lots:
        confidence = 0.85 + (0.05 if len(title_deed_matches) >= 2 else 0)
        logger.info(f"[classifier] TYPE_E detected. Signals: {signals}")
        return ClassifierResult(
            plan_type=PlanType.TYPE_E,
            confidence=min(confidence, 0.95),
            signals=signals,
        )

    # TYPE_C — Engineering/Topo with building layout
    if has_engineering and has_contour_label:
        confidence = 0.85 + (0.05 if has_legend else 0)
        logger.info(f"[classifier] TYPE_C detected. Signals: {signals}")
        return ClassifierResult(
            plan_type=PlanType.TYPE_C,
            confidence=min(confidence, 0.95),
            signals=signals,
        )

    # TYPE_D — Topographic survey only (contours, no significant building layout)
    if has_contour_label and not has_multiple_lots:
        confidence = 0.75
        logger.info(f"[classifier] TYPE_D detected. Signals: {signals}")
        return ClassifierResult(
            plan_type=PlanType.TYPE_D,
            confidence=confidence,
            signals=signals,
            needs_vision_fallback=confidence < FALLBACK_THRESHOLD,
        )

    # TYPE_B — Composite subdivision
    if has_multiple_lots and has_multiple_areas:
        confidence = 0.80 + (0.10 if len(unique_lots) >= 3 else 0)
        logger.info(f"[classifier] TYPE_B detected. Signals: {signals}")
        return ClassifierResult(
            plan_type=PlanType.TYPE_B,
            confidence=min(confidence, 0.95),
            signals=signals,
        )

    # Ambiguous composite: multiple areas but no explicit "Lot N" label
    if has_multiple_areas and not has_multiple_lots:
        confidence = 0.60  # Below fallback threshold → routes to Gemini
        logger.info(f"[classifier] Ambiguous (areas only). Signals: {signals}")
        return ClassifierResult(
            plan_type=PlanType.TYPE_B,
            confidence=confidence,
            signals=signals,
            needs_vision_fallback=True,
        )

    # TYPE_A — Default: simple single parcel (existing working pipeline)
    logger.info(f"[classifier] TYPE_A (default). Signals: {signals}")
    return ClassifierResult(
        plan_type=PlanType.TYPE_A,
        confidence=0.80,
        signals=signals,
    )
