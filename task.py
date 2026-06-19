"""
LandIQ — Kaggle Benchmarks Evaluation Task
==========================================
Task:   landiq-vision-ocr
Tests Gemini's ability to parse Nigerian land survey coordinate text
and return structured JSON coordinate arrays.

Push:   kaggle b t push landiq-vision-ocr -f task.py --wait
Run:    kaggle b t run landiq-vision-ocr -m google/gemini-3-flash-preview --wait
Status: kaggle b t status landiq-vision-ocr
"""

import json
import re
import pandas as pd
import kaggle_benchmarks as kbench


# =============================================================================
# TEST DATA — Nigerian survey plan samples
# =============================================================================

SAMPLES = [
    {
        "survey_name": "Minna UTM Zone 32 Survey",
        "survey_text": (
            "SURVEY PLAN OF PLOT OF LAND AT SAGAMU\n"
            "Surveyed by: T.A. Adeyemi (RLS 789) SURCON REG.\n\n"
            "BEACON          EASTING         NORTHING\n"
            "SC/AK/K 49700   387804.297      550123.450\n"
            "SC/AK/K 49701   387950.123      550200.789\n"
            "SC/AK/K 49702   388100.456      550150.234\n"
            "SC/AK/K 49703   387900.678      550050.123\n\n"
            "AREA: 0.45 HECTARES\n"
            "CRS: MINNA DATUM / UTM ZONE 32N"
        ),
        "expected_count": 4,
    },
    {
        "survey_name": "WGS84 Lagos Decimal Degrees",
        "survey_text": (
            "SURVEY PLAN FOR RESIDENTIAL PLOT\n"
            "Location: Lekki Phase 2, Lagos State\n\n"
            "Point   Latitude      Longitude\n"
            "A       6.4345678     3.5234567\n"
            "B       6.4356789     3.5245678\n"
            "C       6.4367890     3.5256789\n"
            "D       6.4378901     3.5267890\n"
        ),
        "expected_count": 4,
    },
]


# =============================================================================
# TASK DEFINITION
# =============================================================================

@kbench.task(
    name="landiq-vision-ocr",
    description=(
        "Evaluates Gemini's ability to parse Nigerian cadastral survey coordinate "
        "documents and return structured JSON coordinate arrays. Tests the core "
        "intelligence engine powering the LandIQ land risk platform."
    ),
)
def landiq_vision_ocr(llm, survey_text: str, expected_count: int, survey_name: str) -> dict:
    """Parse Nigerian land survey text and extract structured coordinates."""

    prompt = (
        "You are a Geospatial Document Parser for Nigerian land survey plans.\n"
        "Your ONLY job is to extract cadastral coordinate data from the document.\n\n"
        "Rules:\n"
        "- Return ONLY a JSON object. No prose, no markdown, no explanation.\n"
        "- The JSON must have a 'coordinates' key: an array of [easting, northing] or [longitude, latitude] pairs.\n"
        "- Also include 'station_count' (integer) and 'crs_hint' (string or null).\n"
        "- If no coordinates found: {\"coordinates\": [], \"error\": \"No coordinates found\"}\n\n"
        "Example output:\n"
        "{\"coordinates\": [[387804.297, 550123.450], [387950.123, 550200.789]], "
        "\"crs_hint\": \"Minna / UTM Zone 32N\", \"station_count\": 2}\n\n"
        f"--- DOCUMENT START ---\n{survey_text}\n--- DOCUMENT END ---\n\n"
        "Return ONLY valid JSON:"
    )

    with kbench.chats.new(f"landiq-{survey_name}"):
        response = llm.prompt(prompt)

    # Strip markdown fences if present
    raw = response.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # ── Assertion 1: Must be valid JSON ─────────────────────────────────────
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        kbench.assertions.assert_fail(
            expectation=f"[{survey_name}] Response must be valid JSON. Got: {raw[:300]}"
        )
        return {"passed": 0, "total": 3}

    coords = parsed.get("coordinates", [])

    # ── Assertion 2: 'coordinates' key must exist ────────────────────────────
    kbench.assertions.assert_in(
        "coordinates", parsed,
        expectation=f"[{survey_name}] Response JSON must contain a 'coordinates' key"
    )

    # ── Assertion 3: Correct number of coordinate pairs extracted ────────────
    kbench.assertions.assert_equal(
        expected_count, len(coords),
        expectation=(
            f"[{survey_name}] Must extract exactly {expected_count} coordinate pairs, "
            f"got {len(coords)}"
        )
    )

    # ── Assertion 4: Each coordinate is a [number, number] pair ─────────────
    all_valid = all(
        isinstance(c, (list, tuple)) and len(c) == 2
        and all(isinstance(v, (int, float)) for v in c)
        for c in coords
    ) if coords else False

    kbench.assertions.assert_true(
        all_valid,
        expectation=f"[{survey_name}] Each item in 'coordinates' must be a [number, number] pair"
    )

    passed = "coordinates" in parsed and len(coords) == expected_count and all_valid
    return {
        "survey": survey_name,
        "extracted": len(coords),
        "expected": expected_count,
        "crs_hint": parsed.get("crs_hint", "not provided"),
        "passed": int(passed),
        "total": 4,
    }


# =============================================================================
# RUN EVALUATION
# =============================================================================

evaluation_df = pd.DataFrame(SAMPLES)

runs = landiq_vision_ocr.evaluate(
    llm=[kbench.llm],
    evaluation_data=evaluation_df,
    n_jobs=1,
    timeout=120,
)

results = runs.as_dataframe()
print("\n=== LandIQ Vision OCR — Kaggle Evaluation Results ===")
print(results.to_string(index=False))
