"""
LandIQ — agents/tabular_parser.py
Tabular Data Parser for the Cadastral Computation Engine.

Accepts three source types:
  • CSV file bytes (from upload or Google Sheets ?output=csv)
  • XLSX file bytes (from upload)
  • Google Sheets public URL (fetched as CSV)

Returns a list of RawStation dataclasses consumed by cadastral_engine.py.

Rules:
  - Column header matching is case-insensitive.
  - Known aliases: Easting → E, X, EAST; Northing → N, Y, NORTH;
    Station → ID, BEACON, PILLAR, TRIG, SC/.
  - Numeric corruption remediation applied to every value:
      "550,821.575"  → 550821.575   (thousands-comma removal)
      "550852-254"   → 550852.254   (scanner hyphen → decimal)
      "550852,254"   → 550852.254   (European decimal comma)
  - Rows with blank station IDs are auto-labelled (S1, S2 …).
  - Rows with unresolvable Easting/Northing are silently skipped
    and logged in the parse_warnings list.

Zero LLM calls. Zero network calls except parse_sheet_url().
"""

from __future__ import annotations

import csv
import io
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("landiq.tabular_parser")

# ── Column header aliases ─────────────────────────────────────────────────────
_EASTING_ALIASES  = {"easting", "e", "x", "east", "longitude_utm", "utm_e"}
_NORTHING_ALIASES = {"northing", "n", "y", "north", "latitude_utm", "utm_n"}
_STATION_ALIASES  = {"station", "id", "beacon", "pillar", "trig", "name",
                     "station_id", "plot", "corner"}

# Detect station IDs that start with SC/ or similar Nigerian survey prefixes
_STATION_ID_PREFIX = re.compile(r"^(sc|sg|sk|bp|tp|bm|nr)[/\-\s]", re.IGNORECASE)


# ── Data contract ─────────────────────────────────────────────────────────────
@dataclass
class RawStation:
    """One boundary station parsed from tabular data."""
    station_id: str
    easting   : Optional[float] = None
    northing  : Optional[float] = None
    row_index : int = 0         # 0-based row index in source (for error reporting)


# ── Numeric value cleansing ───────────────────────────────────────────────────

def _cleanse_numeric(raw: str) -> Optional[float]:
    """
    Remediate common OCR/scanning corruption patterns and return a float.
    Returns None if the value cannot be interpreted as a number.

    Patterns handled:
      "550,821.575"  → 550821.575  (thousands-comma separator)
      "1,440,000"    → 1440000.0   (multi-group thousands comma)
      "550852-254"   → 550852.254  (hyphen as decimal point)
      "550852,254"   → 550852.254  (European-style decimal comma)
      "550 852.25"   → 550852.25   (space inside number)
    """
    if not raw:
        return None
    s = raw.strip()

    # 1. Remove internal spaces (e.g. "550 821.575")
    s = re.sub(r"(\d)\s+(\d)", r"\1\2", s)

    # 2. Thousands-comma removal: digit + comma + exactly-3 digits NOT followed by another digit
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)

    # 3. If a lone hyphen follows digits with no decimal yet → treat as decimal point
    #    e.g. "550852-254" → "550852.254"
    s = re.sub(r"^(-?\d+)-(\d+)$", r"\1.\2", s)

    # 4. European decimal comma: single comma between digits where comma is not thousands-sep
    #    e.g. "550852,254" → "550852.254"
    #    Only apply if result has exactly one comma
    if "." not in s and s.count(",") == 1:
        s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return None


# ── Column index resolver ─────────────────────────────────────────────────────

def _resolve_columns(headers: list[str]) -> tuple[int | None, int | None, int | None]:
    """
    Determine (station_col, easting_col, northing_col) indices from header row.
    Returns (None, None, None) if no matching headers found.
    """
    station_col = easting_col = northing_col = None
    for idx, h in enumerate(headers):
        key = h.strip().lower()
        if easting_col is None and key in _EASTING_ALIASES:
            easting_col = idx
        elif northing_col is None and key in _NORTHING_ALIASES:
            northing_col = idx
        elif station_col is None and (key in _STATION_ALIASES or _STATION_ID_PREFIX.match(h.strip())):
            station_col = idx
    return station_col, easting_col, northing_col


def _positional_fallback(num_cols: int) -> tuple[int | None, int | None, int | None]:
    """
    Positional heuristic when headers are absent or unrecognised.
    Convention: col 0 = station ID, col 1 = easting, col 2 = northing.
    For 2-column files: col 0 = easting, col 1 = northing (no station ID).
    """
    if num_cols >= 3:
        return 0, 1, 2
    elif num_cols == 2:
        return None, 0, 1
    return None, None, None


# ── CSV parser (core) ─────────────────────────────────────────────────────────

def _rows_to_stations(
    rows: list[list[str]],
    source_label: str = "csv",
) -> tuple[list[RawStation], list[str]]:
    """
    Convert a list of string rows into RawStation objects.
    Returns (stations, warnings).
    """
    if not rows:
        return [], [f"[{source_label}] No rows found in source."]

    warnings: list[str] = []
    stations: list[RawStation] = []

    # Detect if first row is a header
    first = rows[0]
    first_lower = [c.strip().lower() for c in first]

    has_header = any(
        tok in _EASTING_ALIASES | _NORTHING_ALIASES | _STATION_ALIASES
        for tok in first_lower
    )

    if has_header:
        headers = first
        data_rows = rows[1:]
        station_col, easting_col, northing_col = _resolve_columns(headers)
        logger.info(f"[tabular_parser] Header detected. station={station_col} E={easting_col} N={northing_col}")
    else:
        data_rows = rows
        station_col, easting_col, northing_col = _positional_fallback(len(first))
        logger.info(f"[tabular_parser] No header. Positional fallback: station={station_col} E={easting_col} N={northing_col}")

    if easting_col is None or northing_col is None:
        warnings.append(
            f"[{source_label}] Could not identify Easting/Northing columns. "
            "Ensure your file has headers: 'Easting' and 'Northing' (or E/N/X/Y)."
        )
        return [], warnings

    for row_idx, row in enumerate(data_rows):
        if not row or all(c.strip() == "" for c in row):
            continue  # Skip blank rows

        # Station ID
        if station_col is not None and station_col < len(row):
            sid = row[station_col].strip()
        else:
            sid = f"S{row_idx + 1}"

        if not sid:
            sid = f"S{row_idx + 1}"

        # Easting
        if easting_col < len(row):
            easting = _cleanse_numeric(row[easting_col])
        else:
            easting = None

        # Northing
        if northing_col < len(row):
            northing = _cleanse_numeric(row[northing_col])
        else:
            northing = None

        if easting is None or northing is None:
            warnings.append(
                f"[{source_label}] Row {row_idx + 2}: skipped — "
                f"could not parse Easting='{row[easting_col] if easting_col < len(row) else '?'}' "
                f"or Northing='{row[northing_col] if northing_col < len(row) else '?'}'."
            )
            continue

        stations.append(RawStation(
            station_id=sid,
            easting=easting,
            northing=northing,
            row_index=row_idx,
        ))

    logger.info(f"[tabular_parser] Parsed {len(stations)} stations from {source_label}.")
    return stations, warnings


# ── Public API ────────────────────────────────────────────────────────────────

def parse_csv_bytes(file_bytes: bytes) -> tuple[list[RawStation], list[str]]:
    """
    Parse CSV file bytes into RawStation list.
    Returns (stations, warnings).
    """
    try:
        text = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        return _rows_to_stations(rows, source_label="csv")
    except Exception as exc:
        return [], [f"[csv] Parse error: {exc}"]


def parse_xlsx_bytes(file_bytes: bytes) -> tuple[list[RawStation], list[str]]:
    """
    Parse XLSX file bytes into RawStation list using openpyxl.
    Returns (stations, warnings).
    """
    try:
        import openpyxl
    except ImportError:
        return [], ["[xlsx] openpyxl is not installed. Install it with: pip install openpyxl"]

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(cell) if cell is not None else "" for cell in row])
        return _rows_to_stations(rows, source_label="xlsx")
    except Exception as exc:
        return [], [f"[xlsx] Parse error: {exc}"]


def parse_sheet_url(url: str) -> tuple[list[RawStation], list[str]]:
    """
    Fetch a public Google Sheets URL (or any CSV URL) and parse it.
    Automatically appends ?output=csv for Google Sheets links.
    Returns (stations, warnings).
    """
    try:
        import httpx
    except ImportError:
        return [], ["[sheet_url] httpx is not installed."]

    # Google Sheets URL normalisation
    # https://docs.google.com/spreadsheets/d/<ID>/edit → /export?format=csv
    gsheet_match = re.search(
        r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_\-]+)",
        url,
    )
    if gsheet_match:
        sheet_id = gsheet_match.group(1)
        # Check for gid (sheet tab ID)
        gid_match = re.search(r"[#&?]gid=(\d+)", url)
        gid_param = f"&gid={gid_match.group(1)}" if gid_match else ""
        fetch_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv{gid_param}"
    elif "?" not in url and not url.endswith(".csv"):
        fetch_url = url + "?output=csv"
    else:
        fetch_url = url

    try:
        resp = httpx.get(fetch_url, follow_redirects=True, timeout=15.0)
        resp.raise_for_status()
        return parse_csv_bytes(resp.content)
    except Exception as exc:
        return [], [f"[sheet_url] Failed to fetch '{fetch_url}': {exc}"]
