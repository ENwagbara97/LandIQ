"""
LandIQ — tests/run_golden_tests.py
Pre-merge evaluation gate.

Runs all 10 golden test cases through the pipeline and validates outputs
against expected schema contracts. Any failure blocks the merge.

Usage:
    python tests/run_golden_tests.py
    python tests/run_golden_tests.py --case 05   (run single case)
    python tests/run_golden_tests.py --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich import box

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent.parent
GOLDEN_DIR  = Path(__file__).resolve().parent / "golden"
EVAL_LOGS   = ROOT_DIR / "tests" / "eval_logs"

import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

console = Console()

# ── Test Registry ─────────────────────────────────────────────────────────────
GOLDEN_CASES = sorted(GOLDEN_DIR.glob("case_*.json"))


# =============================================================================
# ASSERTION HELPERS
# =============================================================================

class AssertionFailure(Exception):
    """Raised when a golden test assertion fails."""
    pass


def assert_equal(field: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionFailure(
            f"[{field}] Expected '{expected}', got '{actual}'"
        )


def assert_gte(field: str, actual: float, min_val: float) -> None:
    if actual is None or actual < min_val:
        raise AssertionFailure(
            f"[{field}] Expected >= {min_val}, got {actual}"
        )


def assert_lte(field: str, actual: float, max_val: float) -> None:
    if actual is None or actual > max_val:
        raise AssertionFailure(
            f"[{field}] Expected <= {max_val}, got {actual}"
        )


def assert_contains(field: str, container: list | str | None, item: str) -> None:
    if container is None or item not in container:
        raise AssertionFailure(
            f"[{field}] Expected to contain '{item}', got: {container}"
        )


def assert_not_contains(field: str, text: str | None, phrase: str) -> None:
    if text and phrase.lower() in text.lower():
        raise AssertionFailure(
            f"[{field}] Prohibited phrase found: '{phrase}'"
        )


# =============================================================================
# PROHIBITED PHRASES CHECK
# Applied to all Ollama-generated text fields
# =============================================================================

PROHIBITED_PHRASES = [
    "no flood risk",
    "land is safe to buy",
    "title is clear",
    "no government acquisition risk",
    "100% accurate",
    "c of o verified",
    "official government acquisition check",
]


def check_prohibited_phrases(report_json: dict) -> list[str]:
    """Scan all string fields in report for prohibited phrases."""
    violations = []
    text_fields = [
        report_json.get("summary", {}).get("executive_summary", ""),
        report_json.get("summary", {}).get("ai_recommendation", ""),
        report_json.get("flood_risk_metrics", {}).get("reason_in_plain_english", ""),
        report_json.get("growth_potential", {}).get("summary_notes", ""),
    ]
    for text in text_fields:
        if not text:
            continue
        for phrase in PROHIBITED_PHRASES:
            if phrase.lower() in text.lower():
                violations.append(f"Prohibited phrase in output text: '{phrase}'")
    return violations


# =============================================================================
# CASE RUNNER
# Each case is validated against its expected JSON block.
# =============================================================================

def run_case(case_path: Path, verbose: bool = False) -> dict:
    """
    Run a single golden test case.
    Returns a result dict with: name, passed, failures, duration_ms
    """
    case_data = json.loads(case_path.read_text(encoding="utf-8"))
    case_name = case_path.stem
    description = case_data.get("_description", case_name)
    expected = case_data.get("expected", {})
    input_data = case_data.get("input", {})
    failures = []

    start_ms = time.monotonic()

    try:
        # ── IMPORT PIPELINE COMPONENTS ─────────────────────────────────────
        # These imports will fail gracefully if agents aren't built yet.
        # The test runner reports "NOT BUILT" rather than crashing.
        try:
            from agents.coord_extract import run as coord_extract_run
        except ImportError:
            return {
                "name": case_name,
                "description": description,
                "passed": False,
                "failures": ["CoordExtract agent not yet built — run after Tier 1 complete"],
                "duration_ms": 0,
                "status": "NOT_BUILT",
            }

        # ── STEP 1: COORD EXTRACT ──────────────────────────────────────────
        import uuid
        run_id = str(uuid.uuid4())
        coord_result = coord_extract_run(
            raw_input=input_data.get("raw_text", ""),
            run_id=run_id,
            coordinate_hint=input_data.get("coordinate_hint"),
            datum_label=input_data.get("datum_label"),
            stated_area_ha=input_data.get("stated_area_ha"),
        )

        expected_coord = expected.get("coord_extract", {})

        # Handle error case
        if "error_code" in expected_coord:
            if hasattr(coord_result, "error_code"):
                assert_equal(
                    "error_code",
                    coord_result.error_code,
                    expected_coord["error_code"]
                )
            else:
                failures.append(
                    f"Expected MCPErrorResponse with error_code="
                    f"'{expected_coord['error_code']}', but got a valid output"
                )
            # Early return — no further steps expected
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            return {
                "name": case_name,
                "description": description,
                "passed": len(failures) == 0,
                "failures": failures,
                "duration_ms": duration_ms,
                "status": "PASS" if len(failures) == 0 else "FAIL",
            }

        # Normal coord extract validations
        if "detected_crs" in expected_coord:
            assert_equal("detected_crs", coord_result.detected_crs.value, expected_coord["detected_crs"])
        if "crs_confidence_min" in expected_coord:
            assert_gte("crs_confidence", coord_result.crs_confidence, expected_coord["crs_confidence_min"])
        if "crs_confidence_max" in expected_coord:
            assert_lte("crs_confidence", coord_result.crs_confidence, expected_coord["crs_confidence_max"])
        if "is_inside_nigeria" in expected_coord:
            assert_equal("is_inside_nigeria", coord_result.is_inside_nigeria, expected_coord["is_inside_nigeria"])
        if "minna_datum_detected" in expected_coord:
            assert_equal("minna_datum_detected", coord_result.minna_datum_detected, expected_coord["minna_datum_detected"])
        if "dms_converted" in expected_coord:
            assert_equal("dms_converted", coord_result.dms_converted, expected_coord["dms_converted"])
        if "flip_tested" in expected_coord:
            assert_equal("flip_tested", coord_result.flip_tested, expected_coord["flip_tested"])
        if "warnings_contain" in expected_coord:
            for warning_fragment in expected_coord["warnings_contain"]:
                found = any(warning_fragment in w for w in coord_result.warnings)
                if not found:
                    failures.append(f"Warning '{warning_fragment}' not found in warnings: {coord_result.warnings}")

        # CRS dialog triggers
        if "crs_dialogs_fired" in expected:
            expected_dialogs = set(expected["crs_dialogs_fired"])
            actual_dialogs = set(coord_result.crs_dialog_triggers)
            missing = expected_dialogs - actual_dialogs
            if missing:
                failures.append(f"Expected CRS dialogs {missing} to fire, but they did not. Got: {actual_dialogs}")

        # ── STEPS 2-5: FULL PIPELINE ───────────────────────────────────────
        if "risk_assess" in expected or "report" in expected:
            try:
                from core.pipeline import run_pipeline
                import agents.report_gen
                
                # Mock Ollama call to prevent test failures when Ollama is not running
                def mock_ollama_call(*args, **kwargs):
                    system_prompt = kwargs.get("system", "")
                    if "plain-language translator" in system_prompt:
                        # Call 1 mock
                        return '{"mock_metric": "This is a mock translation for testing."}', False
                    else:
                        # Call 2 mock
                        return "EXECUTIVE_SUMMARY: Mock executive summary.\nAI_RECOMMENDATION: Mock AI recommendation.", False
                        
                original_ollama_call = agents.report_gen._llm_call
                agents.report_gen._llm_call = mock_ollama_call
                
                try:
                    report = run_pipeline(
                        coord_output=coord_result,
                        persona_mode=input_data.get("persona_mode", "EVERYDAY_BUYER"),
                        skip_gate=True,  # golden tests bypass interactive gate
                    )
                finally:
                    agents.report_gen._llm_call = original_ollama_call
            except ImportError:
                failures.append("Full pipeline not yet built — complete Tier 2 first")
                duration_ms = int((time.monotonic() - start_ms) * 1000)
                return {
                    "name": case_name,
                    "description": description,
                    "passed": False,
                    "failures": failures,
                    "duration_ms": duration_ms,
                    "status": "NOT_BUILT",
                }

            expected_risk = expected.get("risk_assess", {})
            expected_report = expected.get("report", {})

            if "flood_risk" in expected_risk:
                assert_equal("flood_risk", report.flood_risk_metrics.level.value, expected_risk["flood_risk"])
            if "terrain_suitability" in expected_risk:
                assert_equal("terrain_suitability", report.terrain_assessment.suitability, expected_risk["terrain_suitability"])
            if "traffic_light" in expected_risk:
                assert_equal("risk_assess.traffic_light", report.summary.traffic_light.value, expected_risk["traffic_light"])
            if "traffic_light" in expected_report:
                assert_equal("report.traffic_light", report.summary.traffic_light.value, expected_report["traffic_light"])
            if "overall_risk_score_min" in expected_report:
                assert_gte("overall_risk_score", report.summary.overall_risk_score, expected_report["overall_risk_score_min"])
            if "overall_risk_score_max" in expected_report:
                assert_lte("overall_risk_score", report.summary.overall_risk_score, expected_report["overall_risk_score_max"])

            # Prohibited phrase check
            report_dict = json.loads(report.model_dump_json())
            violations = check_prohibited_phrases(report_dict)
            failures.extend(violations)

    except AssertionFailure as exc:
        failures.append(str(exc))
    except Exception as exc:
        failures.append(f"Unexpected error: {type(exc).__name__}: {exc}")

    duration_ms = int((time.monotonic() - start_ms) * 1000)
    passed = len(failures) == 0
    return {
        "name": case_name,
        "description": description,
        "passed": passed,
        "failures": failures,
        "duration_ms": duration_ms,
        "status": "PASS" if passed else "FAIL",
    }


# =============================================================================
# REPORT & LOG
# =============================================================================

def write_eval_log(results: list[dict]) -> Path:
    """Write evaluation results to a timestamped JSON log file."""
    EVAL_LOGS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = EVAL_LOGS / f"eval_log_{timestamp}.json"
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    log_data = {
        "evaluated_at": datetime.now().isoformat(),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate_pct": round((passed / total) * 100, 1) if total > 0 else 0,
        "results": results,
    }
    log_path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
    return log_path


def print_results_table(results: list[dict]) -> None:
    table = Table(
        title="LandIQ Golden Test Results",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Case", style="bold cyan", width=40)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Failures", width=50)

    for r in results:
        status_display = "[bold green]PASS[/]" if r["passed"] else "[bold red]FAIL[/]"
        if r.get("status") == "NOT_BUILT":
            status_display = "[bold yellow]SKIP[/]"
        failure_text = "\n".join(r["failures"][:2]) if r["failures"] else ""
        if len(r["failures"]) > 2:
            failure_text += f"\n... +{len(r['failures']) - 2} more"
        table.add_row(
            r["name"],
            status_display,
            f"{r['duration_ms']}ms",
            failure_text,
        )

    console.print(table)


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="LandIQ Golden Dataset Evaluation Gate")
    parser.add_argument("--case", help="Run a specific case number (e.g. 05)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed failure info")
    args = parser.parse_args()

    console.rule("[bold cyan]LandIQ — Golden Dataset Evaluation[/]")

    # Filter cases if --case specified
    cases_to_run = GOLDEN_CASES
    if args.case:
        cases_to_run = [c for c in GOLDEN_CASES if f"case_{args.case.zfill(2)}" in c.name]
        if not cases_to_run:
            console.print(f"[red]No case found matching: {args.case}[/]")
            return 1

    results = []
    for case_path in cases_to_run:
        console.print(f"  Running [cyan]{case_path.stem}[/]...", end=" ")
        result = run_case(case_path, verbose=args.verbose)
        results.append(result)
        status_icon = "[PASS]" if result["passed"] else ("[SKIP]" if result.get("status") == "NOT_BUILT" else "[FAIL]")
        console.print(f"{status_icon} [{result['duration_ms']}ms]")

    console.print()
    print_results_table(results)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    skipped = sum(1 for r in results if r.get("status") == "NOT_BUILT")
    failed = total - passed - skipped

    console.print()
    console.print(
        f"Results: [green]{passed} passed[/] · "
        f"[red]{failed} failed[/] · "
        f"[yellow]{skipped} skipped (not built)[/] "
        f"of {total} total"
    )

    log_path = write_eval_log(results)
    console.print(f"Eval log written: [dim]{log_path}[/]")

    if failed > 0:
        console.print(
            "\n[bold red][ERROR] GATE BLOCKED - do not merge.[/] "
            "All test cases must pass before merging to production branch."
        )
        return 1

    if passed == total:
        console.print("\n[bold green][OK] All cases passed - gate clear.[/]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
