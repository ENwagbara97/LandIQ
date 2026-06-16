# LandIQ — Land Risk Intelligence Agent (Nigeria)
## Unified Operational Plan · v2.0 · Local-First MVP · Zero Cloud Dependency
**Synthesized from:** LANDIQ MASTER SYSTEM PROMPT v1.0 · `LandRisk_Nigeria_SystemArchitecture.docx` · LANDIQ MASTER SYSTEM ARCHITECTURE SPECIFICATION v2.0
**Last updated:** 2026-06-04 | **Status:** Canonical Reference — Build-Ready

---

> [!IMPORTANT]
> **RUNTIME CONFLICT — PERMANENTLY RESOLVED**
> The `.docx` specification originally listed `Anthropic Claude claude-sonnet-4-20250514` as the AI Orchestrator.
> **Resolution (non-negotiable):** Claude is fully deprecated for this phase. All LLM calls route exclusively to **Ollama running locally** (`llama3` or `mistral`). No cloud LLM API calls are made at any point in the pipeline. This maximises data privacy and eliminates API costs.

---

## 1. Product Vision

Nigeria's land market operates on catastrophic information asymmetry. Buyers commit millions of Naira to land parcels with no systematic risk screening — no flood check, no government acquisition alert, no encroachment scan, no coordinate validation. The result: demolished buildings, flooded investments, years-long court disputes, and total capital loss.

**LandIQ is "Carfax for Land."** A user uploads any combination of survey plan (PDF/image), coordinates (manual entry or file), KML/KMZ, or shapefile. The AI agent pipeline automatically generates a structured Land Intelligence Report within 5 minutes.

You combine the absolute structural rigor of a senior Geomatics/GIS engineer with the plain-spoken, humanized communication style required to protect a first-time Nigerian property buyer from catastrophic financial loss.

**You completely decouple unpredictable LLM reasoning from mathematical geomatics calculations. Python does the math. Ollama does the plain-English synthesis.**

---

## 2. Architecture Decision Log

| Concern | Original `.docx` | v1.0 Prompt | v2.0 Spec | **Final Decision** |
|---|---|---|---|---|
| LLM Runtime | Anthropic Claude (cloud) | Ollama (local) | Ollama (local) | **✅ Ollama — llama3 / mistral** |
| State Engine | PostgreSQL | Not specified | SQLite (lean) | **✅ SQLite for session state · PostgreSQL for spatial data** |
| OCR | Google Vision API or Tesseract | Tesseract | Tesseract | **✅ Tesseract (local) — no cloud OCR at MVP** |
| GIS Backend | GeoPandas + Shapely + GDAL | Same | Same | **✅ GeoPandas + Shapely + GDAL** |
| Tool Interface | None specified | None specified | MCP JSON-RPC | **✅ MCP pattern — atomic tools with JSON-RPC schemas** |
| Frontend | Next.js 14 + Tailwind | Not specified | Not specified | **✅ Next.js 14 + Tailwind CSS** |
| Map | Mapbox GL JS or Leaflet | Leaflet + OSM | Leaflet + OSM | **✅ Leaflet + OSM tiles (free, local-compatible)** |
| Backend API | FastAPI (Python) | FastAPI | FastAPI | **✅ FastAPI** |
| DB (Spatial) | PostgreSQL + PostGIS | PostgreSQL + PostGIS | Not specified | **✅ PostgreSQL + PostGIS** |
| DB (Session) | Not specified | Not specified | SQLite | **✅ SQLite for real-time session state** |
| Job Queue | Celery + Redis | Celery + Redis | Not specified | **✅ Celery + Redis** |
| PDF Output | WeasyPrint / Puppeteer | WeasyPrint | WeasyPrint | **✅ WeasyPrint** |
| Auth | Supabase Auth | Supabase Auth | Not specified | **✅ Supabase Auth** |
| Payments | Paystack | Paystack | Not specified | **✅ Paystack (NGN)** |
| Security | Not specified | Not specified | Input sanitization + HITL | **✅ Input scrubber + Output leak scrubber + HITL sinks** |

---

## 3. Operating Context (Non-Negotiable Parameters)

| Parameter | Value |
|---|---|
| Country | Federal Republic of Nigeria |
| Primary CRS | WGS84 (EPSG:4326) |
| Supported CRS | UTM Zone 31N (EPSG:32631) · 32N (EPSG:32632) · 33N (EPSG:32633) · Minna Datum (EPSG:4263) → mandatory transform to WGS84 |
| Nigeria Bounding Box | Lon 2.67–14.68 · Lat 4.24–13.88 |
| Language (user-facing) | Plain English — **zero GIS jargon in any output field** |
| Currency | Nigerian Naira (NGN ₦) |
| LLM Runtime | **Ollama (local)** — llama3 or mistral |
| GIS Backend | Python / GeoPandas / Shapely / GDAL |
| Data Sources | SRTM DEM · HydroSHEDS · Sentinel-2 · OpenStreetMap (Overpass API) · FMARD |
| Mandatory Disclaimer | *"This report is advisory only. It does not constitute a legal survey, title opinion, or professional engineering assessment. Always engage a SURCON-registered surveyor and a qualified property lawyer before committing funds to any land transaction."* |

---

## 4. Persona-Driven Product Mission

The system's outputs must satisfy five distinct local user personas simultaneously, without exposing any persona to technical jargon intended for another:

| # | Persona | Core Need | What LandIQ Delivers |
|---|---|---|---|
| 1 | **Registered Surveyor** | Hyper-accurate CRS detection, flawless polygon closure, strict conversion flags | Confidence score on CRS, Minna Datum flag with `[POS_ACCURACY: ±5 METRES]`, polygon closure validation |
| 2 | **Property Developer** | Institutional-grade identification of committed government acquisitions and overlapping surveys | Advisory flags on acquisition proximity signals, encroachment detection, open data caveat |
| 3 | **Architect** | Rapid site layout safety: slope assessment, terrain boundary, drainage feasibility | `steepness_of_land`, `terrain_difficulty`, suitability rating, drainage advisory flags |
| 4 | **Realtor** | Professional, downloadable, visually authoritative PDF tool to establish credibility with buyers | WeasyPrint-rendered branded PDF with traffic light, map screenshot, full report |
| 5 | **Everyday Land Buyer** | Humanized, zero-jargon summary: is my money safe or am I buying a swamp? | 3-sentence executive summary, traffic light, plain-English AI recommendation with legal disclaimer |

---

## 5. Multi-Agent Pipeline — NEVER SKIP · NEVER REORDER · NEVER COLLAPSE

```
[User Upload: Survey Plan / Coords / KML / Shapefile]
              │
              ▼
    ┌─────────────────────────┐
    │  STEP 0: SANITIZATION   │ ◄── Input Scrubber + Prompt Injection Filter
    │  & CONFIRMATION GATE    │ ◄── Map Preview + "Is this your land?" Gate
    └─────────────────────────┘
              │  [boolean YES confirmed + run_id assigned]
              ▼
    ┌─────────────────────────┐
    │  STEP 1: CoordExtract   │ ◄── Python: Tesseract OCR + CRS heuristics
    │  Agent                  │     MCP Tool: CoordExtractTool (JSON-RPC)
    └─────────────────────────┘
              │
              ▼
    ┌─────────────────────────┐
    │  STEP 2: GISAnalysis    │ ◄── Python: GeoPandas / Shapely / GDAL
    │  Agent                  │     MCP Tool: GISAnalysisTool (JSON-RPC)
    └─────────────────────────┘
              │
              ▼
    ┌─────────────────────────┐
    │  STEP 3: RiskAssess     │ ◄── Python: Deterministic rule engine only
    │  Agent                  │     NO LLM CALL — hard math boundary
    └─────────────────────────┘
              │
              ▼
    ┌─────────────────────────┐
    │  STEP 4: Suitability    │ ◄── Python: OSM buffer + density calculations
    │  Growth Agent           │     MCP Tool: LocalDBTool (JSON-RPC)
    └─────────────────────────┘
              │
              ▼
    ┌─────────────────────────┐
    │  STEP 5: ReportGen      │ ◄── Python fills schema → Ollama synthesis
    │  Agent                  │     Output scrubber runs before delivery
    └─────────────────────────┘
              │
              ▼
    [Output Leak Scrubber] → [Pydantic Schema Validation]
              │
              ▼
    [WeasyPrint HTML-to-PDF Engine]
              │
              ▼
    [User Download / Shareable Link / Dashboard]
```

---

### STEP 0 — Sanitization Filter & User Confirmation Gate

> [!CAUTION]
> Analysis is **completely frozen** until this gate emits a logged boolean `YES` confirmation. Zero exceptions. No partial bypasses.

**Sequence (in strict order):**

1. **Input Sanitization Filter** *(runs first, before any parsing)*
   - Route all textual input and file processing results through an isolated classification layer
   - Scan for: system override syntax, instruction bypass scripts, destructive command keywords, prompt injection patterns
   - On detection → drop request instantly, generate `[EXECUTION_HAZARD]` notification, do not proceed
   - On clean → pass to Step 1 parsing

2. **Coordinate Extraction Preview**
   - Render extracted coordinates on local Leaflet satellite map
   - Confirm parcel boundaries form a valid closed polygon loop inside the Nigeria Bounding Box
   - Display detected CRS with confidence score

3. **User Confirmation**
   - Prompt: *"Is this your land boundary?"*
   - User must click explicit **YES** → logs boolean confirmation + assigns unique `run_id`
   - If **NO** → stop, ask user to correct input
   - If any Coordinate Dialog Trigger fires (see Section 9) → surface dialog and await resolution

4. **`run_id` Assignment**
   - Generate a unique identifier string for this execution
   - Thread through every prompt call, tool invocation, and data conversion step
   - Store in SQLite session state

---

### STEP 1 — CoordExtract Agent

**Runtime:** Python (Tesseract OCR + regex + GeoPandas) + MCP `CoordExtractTool` — **no LLM call**

**Input:** Raw file bytes (PDF, image, KML, KMZ, shapefile) OR manual coordinate string

**Tasks:**
1. Tesseract OCR if image/PDF — extract all numeric pairs matching coordinate patterns (DD, DMS, UTM Northing/Easting)
2. Strip noise, normalise strings, identify format (DMS vs Decimal Degrees), check formatting errors
3. Detect most likely CRS using heuristics:
   - Values 3.0–15.0 / 4.0–14.0 → likely WGS84 Lat/Lng
   - Northing 600,000–900,000, Easting 200,000–900,000 → likely UTM Nigeria zone
   - Label `MINNA` or `Clarke 1880` → Minna Datum; force `pyproj` transform to WGS84 + inject `[POS_ACCURACY: ±5 METRES]` flag
4. Return detected CRS with confidence score (0–100)
5. Return coordinate array as WGS84 Lat/Lng
6. Compute parcel centroid and bounding box
7. **Auto-flip Failsafe:** If `is_inside_nigeria = false`, automatically test flipped Easting/Northing pair. If flipped pair lands within bbox → halt and trigger Dialog T2. Do not proceed silently.

**Output Contract (Pydantic-validated before handoff):**
```json
{
  "coordinates": [[6.4281, 3.4219], ["..."]],
  "centroid": { "lat": 6.4281, "lng": 3.4219 },
  "detected_crs": "WGS84",
  "crs_confidence": 87.5,
  "is_inside_nigeria": true,
  "computed_area_ha": 2.4,
  "warnings": []
}
```

**MCP Error Response Structure (on failure):**
```json
{
  "status": "error",
  "error_code": "POLYGON_OPEN",
  "instruction": "The extracted points do not form a closed loop. Check for a missing terminal node or typo in point sequence."
}
```

---

### STEP 2 — GISAnalysis Agent

**Runtime:** Python (GeoPandas + Shapely + GDAL + local raster/vector files) + MCP `GISAnalysisTool` — **no LLM call**

**Input:** Validated WGS84 coordinates + centroid + bounding box

**Data Sources (query in order, cache results locally):**
1. **SRTM 30m DEM** via local offline raster or AWS Terrain Tiles → elevation at centroid, min/max within parcel, mean slope
2. **HydroSHEDS (HydroRIVERS)** → distance to nearest watercourse (m), Strahler order
3. **OpenStreetMap (Overpass API)** → distance to nearest paved road, town centre, hospital, electricity infrastructure
4. **Sentinel-2** (SentinelHub or GEE — 2020 + latest) → NDWI, NDVI, new structures in 200m buffer by epoch comparison

**Python-computed indicators:**
- `flood_proximity_score` — weighted function: `ƒ(elevation_m, distance_to_river_m, slope_pct)`
- `terrain_difficulty` — slope classification: 0–5% = flat · 5–15% = gentle · >15% = steep
- `encroachment_flag` — boolean: new built-up area detected in buffer since 2020
- `road_access_category` — Excellent (<200m) · Good (200–500m) · Fair (500–1km) · Poor (>1km)

**Output Contract:**
```json
{
  "elevation_m": 12.4,
  "slope_pct": 3.1,
  "distance_to_river_m": 820,
  "river_strahler_order": 2,
  "flood_proximity_score": 0.31,
  "terrain_difficulty": "gentle",
  "distance_to_road_m": 340,
  "road_access_category": "Good",
  "distance_to_town_m": 2100,
  "encroachment_flag": false,
  "encroachment_detail": "No new structures detected in 200m buffer (2020–2024)",
  "ndwi": 0.08,
  "ndvi": 0.42,
  "data_confidence": 76.0
}
```

---

### STEP 3 — RiskAssess Agent

**Runtime:** Python (pure deterministic rule engine) — **no LLM call — absolute hard boundary**

> [!WARNING]
> Risk classification is **100% deterministic Python code**. The LLM must never be asked to classify, infer, or guess flood risk or terrain suitability. These are rule engines, not language model tasks. Any attempt to pass these decisions to Ollama is a critical architecture violation.

**Input:** GISAnalysis output object

**Flood Risk Classification:**

| Level | Trigger Condition — ANY one condition triggers the level |
|---|---|
| **HIGH** | `elevation_m < 5` **AND** `distance_to_river_m < 500` |
| **HIGH** | `flood_proximity_score > 0.7` |
| **HIGH** | `ndwi > 0.3` (persistent water signature) |
| **HIGH** | `river_strahler_order >= 4` **AND** `distance_to_river_m < 300` |
| **MEDIUM** | `elevation_m` 5–15m **AND** `distance_to_river_m < 1000` |
| **MEDIUM** | `flood_proximity_score` 0.4–0.7 |
| **MEDIUM** | `slope_pct < 3` (flat land — poor drainage aggregation) |
| **LOW** | Does not meet any HIGH or MEDIUM condition |

**Terrain Suitability:**

| Level | Condition |
|---|---|
| **SUITABLE** | `slope_pct < 15` AND `elevation_m > 3` |
| **MARGINAL** | `slope_pct` 15–25% OR `elevation_m` 1–3m |
| **UNSUITABLE** | `slope_pct > 25` OR `elevation_m < 1` |

**Development Suitability Matrix:**

| Use Type | Required Conditions |
|---|---|
| Residential | flood LOW/MEDIUM + terrain SUITABLE/MARGINAL + road Good/Excellent |
| Commercial | flood LOW + terrain SUITABLE + road Excellent |
| Agricultural | Any flood + any terrain (flag drainage requirements if MEDIUM/HIGH) |
| Industrial | flood LOW + terrain SUITABLE + road Excellent + no residential settlement within 500m |

**Advisory Flags (Python-triggered, Ollama-narrated in plain English):**
- `encroachment_flag = true` → flag for physical site inspection
- `ndwi > 0.1` in dry season → possible wetland, check FMARD classification
- `ndvi > 0.6` → dense vegetation, check if gazetted forest reserve

**Output Contract:**
```json
{
  "flood_risk": "LOW",
  "flood_risk_reason": "string",
  "flood_confidence": 76.0,
  "terrain_suitability": "SUITABLE",
  "development_suitability": {
    "residential": true,
    "commercial": false,
    "agricultural": true,
    "industrial": false
  },
  "advisory_flags": [],
  "overall_risk_score": 28.0
}
```

---

### STEP 4 — SuitabilityGrowth Agent

**Runtime:** Python (OSM queries + density calculations) + MCP `LocalDBTool` — **no LLM call**

**Input:** RiskAssess output + GISAnalysis output + centroid coordinates

**Tasks:**
1. Cross-reference centroid with OSM land use layers (settlement boundary, forest, wetland, protected area)
2. Distance to nearest urban centroid (SEDAC GPW dataset)
3. Urban expansion proxy: building density in 1km, 5km, 10km buffer rings via OSM building footprints — density trend = growth signal
4. Infrastructure proximity: road corridor within 2km, airport/port/rail within 5km

**Growth Potential Classification:**

| Level | Condition |
|---|---|
| **HIGH** | Urban ring growth >15% + infrastructure within 2km |
| **MEDIUM** | Urban ring growth 5–15% OR infrastructure within 5km |
| **LOW** | Remote, minimal growth signals |

**Output Contract:**
```json
{
  "land_use_conflicts": [],
  "urban_expansion_score": 0.54,
  "infrastructure_proximity": {
    "road_km": 0.34,
    "airport_km": 12.1,
    "rail_km": null
  },
  "growth_potential": "MEDIUM",
  "growth_notes": "string"
}
```

---

### STEP 5 — ReportGen Agent

**Runtime:** Python schema assembly → **Ollama (llama3/mistral) for synthesis only** → Output Leak Scrubber → Pydantic validation

> [!NOTE]
> **The four and only four tasks Ollama is called for:**
> 1. Plain-English translation of GIS numeric outputs into user-facing narrative text
> 2. Executive summary generation (3 sentences maximum)
> 3. AI recommendation paragraph
> 4. Advisory flag narrative interpretation
>
> **All JSON fields, risk scores, traffic light, and boolean flags are set deterministically by Python before the LLM is invoked. The LLM fills text fields only.**

**Python responsibilities (before any Ollama call):**
- Assign traffic light using deterministic rules:
  - **GREEN** — flood LOW + terrain SUITABLE + zero advisory flags
  - **AMBER** — flood MEDIUM OR any single advisory flag
  - **RED** — flood HIGH OR terrain UNSUITABLE OR 2+ advisory flags
- Populate all structured schema fields
- Flag every indicator where `data_confidence < 50` with `[LOW DATA]`
- Return `null` for any risk score where `data_confidence < 30` → add to `advisory_flags`: *"Insufficient data. Manual inspection required."*

**Ollama context constraints:**
- Pass only the strict prerequisite JSON slice — **keep each sub-agent prompt under 2,000 tokens**
- Do NOT feed historical payload or prior agent outputs to downstream Ollama calls
- LLM writes: `executive_summary` (≤3 sentences), `ai_recommendation`, `growth_notes`, `reason_in_plain_english`

**Tone rules (enforced for all Ollama outputs):**
- Never alarming, never dismissive
- One risk per sentence in the executive summary
- **GIS jargon → plain English replacements:**

| Internal Field | User-Facing Text |
|---|---|
| `distance_to_river_m` | "distance to nearest river" |
| `slope_pct` / `steepness_of_land` | "steepness of the land" |
| `ndwi` / `water_presence_index` | "water presence index" |
| DEM / elevation data | "elevation data" |
| Strahler order | *(omit — never user-facing)* |
| `flood_proximity_score` | "flood exposure rating" |
| `data_confidence` | "data confidence score" |

- Always end `ai_recommendation` with: *"This report is advisory. Engage a SURCON-registered surveyor and a qualified property lawyer before committing any funds."*

**Traffic light plain-language labels:**
- GREEN → *"Proceed with standard due diligence"*
- AMBER → *"Proceed with caution — review flagged items"*
- RED → *"Do not proceed without expert site assessment"*

---

## 6. Python vs. LLM — Definitive Task Boundary Table

| Task | Runtime | Rationale |
|---|---|---|
| Prompt injection detection | **Python (sanitization layer)** | Rule-based keyword classification |
| OCR coordinate extraction | **Python (Tesseract + regex)** | Deterministic pattern matching |
| CRS detection & confidence scoring | **Python** | Heuristic numeric range checks |
| Minna Datum → WGS84 transform | **Python (pyproj)** | Mathematical coordinate transform |
| `[POS_ACCURACY: ±5 METRES]` flag injection | **Python** | Hard-coded precision warning |
| DMS → Decimal Degrees conversion | **Python** | Pure arithmetic |
| Easting/Northing auto-flip test | **Python** | Point-in-polygon bbox check |
| Nigeria bounding box check | **Python** | Point-in-polygon |
| Polygon closure validation | **Python (Shapely)** | Geometric closed-loop check |
| Area computation | **Python (Shapely)** | Geometric calculation |
| Area discrepancy check | **Python** | Arithmetic comparison |
| SRTM elevation extraction | **Python (rasterio/GDAL)** | Raster data extraction |
| Slope calculation | **Python (numpy/GDAL)** | Terrain derivative from DEM |
| HydroSHEDS river distance | **Python (GeoPandas)** | Nearest-feature spatial join |
| `flood_proximity_score` calculation | **Python** | Weighted numeric formula |
| NDWI / NDVI computation | **Python** | Sentinel-2 band math |
| Encroachment detection | **Python** | Multi-epoch change detection |
| OSM feature distance queries | **Python (Overpass API client)** | Spatial proximity queries |
| Urban expansion density rings | **Python** | OSM footprint density math |
| Flood risk classification | **Python (rule engine)** | Deterministic threshold matrix |
| Terrain suitability classification | **Python (rule engine)** | Deterministic threshold matrix |
| Development suitability matrix | **Python (rule engine)** | Boolean logic on GIS outputs |
| Growth potential classification | **Python (rule engine)** | Density + proximity thresholds |
| Traffic light assignment | **Python (rule engine)** | Deterministic from risk levels |
| JSON schema population | **Python** | All numeric/boolean fields filled before LLM |
| Schema validation | **Python (Pydantic)** | Schema enforcement at every agent boundary |
| `run_id` generation & threading | **Python** | UUID4 per execution |
| Circuit breaker enforcement | **Python (host loop)** | 3-call limit counter |
| Output path/port/secret scrubbing | **Python (output scrubber)** | Regex erasure before delivery |
| Executive summary text | **Ollama (llama3/mistral)** | Natural language generation |
| AI recommendation paragraph | **Ollama (llama3/mistral)** | Natural language generation |
| Advisory flag narrative | **Ollama (llama3/mistral)** | Plain-English interpretation |
| GIS jargon → plain English | **Ollama (llama3/mistral)** | Language translation |

---

## 7. MCP Tool Interface Architecture

To enforce absolute runtime efficiency on constrained local hardware, every Python-backed utility is compiled as an **atomic, standalone tool** exposing a strictly enforced JSON-RPC schema interface. The MCP design pattern separates the orchestrating FastAPI client from the tool execution layer.

```
              ┌────────────────────────────────────────────┐
              │               MCP CLIENT                   │
              │       (Local Engine / FastAPI Host)         │
              └──────────┬────────────────────▲────────────┘
                         │                    │
            JSON-RPC Request (Validate)   JSON-RPC Response (Output)
                         │                    │
                         ▼                    │
              ┌────────────────────────────────────────────┐
              │               MCP SERVER                   │
              │  ┌──────────────────┐ ┌─────────────────┐  │
              │  │ CoordExtractTool │ │ GISAnalysisTool │  │
              │  └──────────────────┘ └─────────────────┘  │
              │  ┌──────────────────┐ ┌─────────────────┐  │
              │  │   LocalDBTool    │ │  RiskRuleTool   │  │
              │  └──────────────────┘ └─────────────────┘  │
              └────────────────────────────────────────────┘
```

**Architecture Rules:**

1. **Granular Task Encapsulation** — Every utility (OCR reader, raster lookup, polygon closure check) is an atomic tool with a strictly enforced JSON-RPC schema. Tools declare what they execute — never how they are internally implemented.

2. **Strict Ollama Context Boundaries** — The orchestrator passes only the relevant JSON sub-schema per agent call. Historical payloads are never forwarded to downstream agents. Maximum 2,000 tokens per sub-agent prompt.

3. **Structured Error Payloads** — MCP tools never throw unhandled stack traces. All errors return a structured correction tip:

```json
{
  "status": "error",
  "error_code": "POLYGON_OPEN",
  "instruction": "The extracted points do not form a closed loop. Check for a missing terminal node or typo in point sequence."
}
```

```json
{
  "status": "error",
  "error_code": "CRS_UNDETECTABLE",
  "instruction": "No recognisable CRS heuristic matched. Prompt the user to manually select: WGS84 / Minna Datum / UTM 31N / 32N / 33N."
}
```

```json
{
  "status": "error",
  "error_code": "RASTER_UNAVAILABLE",
  "instruction": "SRTM tile for this bbox is not cached locally. Flag elevation_m as [UNAVAILABLE] and add to advisory_flags."
}
```

---

## 8. Local Agent Quality & Evaluation Engine

Because local open-source models lack the safety margins of massive cloud clusters, quality control is enforced inside the code pipeline before any change reaches production.

### 8.1 — The Local Golden Dataset

Maintain an offline collection of **30 complex test variations**, covering:

| Category | Test Cases |
|---|---|
| Swapped Easting/Northing | 5 cases from different Nigerian zones |
| Unclosed boundary polygons | 4 cases with single missing terminal node |
| High-risk flood zones | 5 genuine swamp surveys from Lekki, Niger Delta, Benue floodplain |
| Varying input formats | Raw DMS text blocks · clean KML files · noisy OCR strings · shapefiles |
| Minna Datum inputs | 4 cases with expected `[POS_ACCURACY: ±5 METRES]` flag |
| Low data confidence | 4 cases where `data_confidence < 30` → verify `null` output + advisory flag |
| Edge cases | 4 cases at or near Nigeria bounding box boundary |
| Clean passes | 4 straightforward valid inputs for regression |

### 8.2 — Pre-PR Evaluation Gate Workflow

> [!CAUTION]
> **No prompt tweak, system parameter update, or code adjustment may be merged to the production branch without executing the full local evaluation pipeline.** Run comparison metrics must be logged directly into the version control commit.

**Gate steps:**
1. Run full golden dataset through the updated pipeline
2. Compare structured JSON outputs against expected schema contracts
3. Check traffic light assignments match expected outcomes
4. Verify no prohibited phrases appear in any text field
5. Log pass/fail metrics per test case into `eval_log_{timestamp}.json`
6. Block merge if any test case fails a hard assertion

### 8.3 — Glass-Box Trajectory Evaluation

The local testing framework parses and grades the **complete structural journey of tool choices**:
- If an agent executes an irrelevant tool function → hard failure
- If an agent jumps steps out of sequence → hard failure
- If the pipeline completes without a logged `run_id` thread → hard failure

### 8.4 — LLM-as-Judge Protocol

Configure a dedicated Pytest evaluation profile. After each agent execution:
1. A separate high-fidelity local Ollama model instance inspects the output schema
2. Flags any residual technical GIS jargon in user-facing text fields
3. Checks for hallucinated land safety terms (prohibited phrases list)
4. Verifies `advisory_flags` is populated instead of returning `null` on missing data
5. Assigns a structured **pass/fail grade** with a compliance score against the system specification

---

## 9. Local Observability, Sessions & State Separation

### 9.1 — Strict Session State Partitioning

Real-time conversational parameters and file states must **never reside in application-layer memory**. All persistence routes to the local state database:

| Data Type | Storage | Retention |
|---|---|---|
| Active session coordinates | SQLite (session DB) | Duration of session |
| `run_id` thread | SQLite (session DB) | Duration of run |
| Long-term report history | PostgreSQL + PostGIS | User account lifetime |
| User PII (name, phone) | Supabase Auth layer only | Never in report JSON |
| Raw uploaded files | S3 / Supabase Storage | 24 hours — then HITL-confirmed deletion |
| Last 5 report IDs | SQLite (session DB) | Dashboard display |

Long-term interactions are compressed to procedural memory summaries before being passed to any prompt context — keeping input payloads fast and lightweight.

### 9.2 — Structured Run Tracking

Every execution request generates a unique `run_id` (UUID4). This identifier is threaded through:
- Every Pydantic schema payload at each agent boundary
- Every MCP tool invocation log entry
- Every data conversion step
- The final report JSON `meta.report_id` field

### 9.3 — Token Loop Circuit Breakers

> [!WARNING]
> Local open-source models can enter execution cycles. The host application loop enforces a hard circuit breaker.

**Rule:** If any sub-agent attempts more than **3 sequential tool invocations** without delivering a valid structured output:
1. Abort execution immediately
2. Flag `[SYSTEM_INF_LOOP]` warning in the session log
3. Step down gracefully — surface a human triage notification
4. Do **not** retry automatically

---

## 10. Defensive Security & Containment

### 10.1 — Input Sanitization Layer (Step 0, first action)

- Route every textual user input or file processing result through an isolated classification layer **before** passing to any agent
- Detection targets: system override syntax · instruction bypass scripts · destructive command keywords · prompt injection patterns
- On detection → drop request instantly → generate `[EXECUTION_HAZARD]` notification → halt pipeline

### 10.2 — Output Leak Scrubbers (Step 5, last action before delivery)

Before returning any payload to the interface layer, sanitize all string blocks:
- Erase all explicit local file paths
- Erase private server ports
- Erase local database access parameters or connection strings
- Erase internal debug variables or stack trace fragments

### 10.3 — Human-In-The-Loop (HITL) Sinks

High-risk or irreversible actions require physical human confirmation:

| Trigger | HITL Action |
|---|---|
| Uploaded document cache older than 24 hours | Freeze deletion. Display physical confirmation button. User must click **"Yes, delete"**. |
| Any file write operation outside designated output directory | Halt. Surface alert. Require explicit approval. |
| `[EXECUTION_HAZARD]` flagged on input | Block pipeline. Display hazard notification. Require re-submission. |

---

## 11. Coordinate System Dialog Logic — Mandatory Guardrails

> [!CAUTION]
> These dialogs are **mandatory**. Analysis halts until the user resolves each triggered dialog. No exceptions, no silent bypasses.

| # | Trigger | Dialog Message | User Options |
|---|---|---|---|
| T1 | `crs_confidence < 60` | ⚠️ *"We could not confidently identify your coordinate system. Please confirm which system was used on your survey plan."* | WGS84 / Minna Datum / UTM 31N / UTM 32N / UTM 33N |
| T2 | `is_inside_nigeria = false` (after auto-flip test) | ⚠️ *"These coordinates fall outside Nigeria. A common cause is Easting and Northing being swapped. Please review."* | Swap Easting/Northing / Re-enter manually / Proceed anyway |
| T3 | Area discrepancy > 10% | ⚠️ *"The area we computed from your coordinates differs from the stated area by [X]%. One or more coordinates may be missing or incorrect."* | Continue / Review coordinates / Upload new plan |
| T4 | Minna Datum detected | ℹ️ *"Minna Datum detected. We will convert to WGS84 for analysis. Position accuracy: ±5 metres."* | Confirm / Cancel |
| T5 | DMS format detected | ℹ️ *"Degrees-Minutes-Seconds format detected. We have converted to Decimal Degrees. Please confirm."* | Confirm / Enter manually |

---

## 12. Prohibited Outputs — Enforced Across All Agents & All Output Fields

> [!CAUTION]
> These phrases must **never** appear in any agent output, report schema field, PDF text, or user-facing string.

| ❌ Prohibited | ✅ Required Substitute |
|---|---|
| "No flood risk" | "Low estimated flood risk based on elevation and river proximity data" |
| "Land is safe to buy" | "Physical indicators are favourable. Engage a surveyor and lawyer for legal due diligence." |
| "Title is clear" | "Advisory report only — always verify document authenticity directly at the state registry." |
| "No government acquisition risk" | "No acquisition signals detected in available open data. Verify at Surveyor-General's office." |
| "C of O verified" | *(Not in scope at MVP — never reference)* |
| "100% accurate" | Show explicit confidence score: *"Confidence: 84% — based on 30m resolution terrain data"* |
| "Official government acquisition check" | "Physical land suitability screener using satellite and terrain data" |
| Any risk score when `data_confidence < 30` | Return `null` → add `"[FIELD_NAME]: Insufficient data. Manual inspection required."` to `advisory_flags` |
| Free-form text as the root output | Always return JSON exactly matching the v2.0 ReportSchema |

---

## 13. v2.0 Report Schema (JSON Contract — All Agents Must Honour)

All agents produce typed JSON. The schema below is the **authoritative contract** between agents and the WeasyPrint PDF renderer. Agents fill fields — they do not invent new fields. All field names in user-facing sections use plain English.

```json
{
  "meta": {
    "report_id": "uuid4-string",
    "generated_at": "2024-11-14T10:32:00Z",
    "version": "2.0",
    "disclaimer": "This report is advisory only. It does not constitute a legal survey, title opinion, or professional engineering assessment. Always engage a SURCON-registered surveyor and a qualified property lawyer before committing funds to any land transaction."
  },

  "parcel_geometry": {
    "centroid": { "lat": 6.4281, "lng": 3.4219 },
    "coordinates": [[6.4281, 3.4219], ["..."]],
    "computed_area_ha": 2.4,
    "stated_area_ha": null,
    "location_context": {
      "lga": "Epe",
      "state": "Lagos",
      "community": null
    }
  },

  "coordinate_validation": {
    "detected_crs": "WGS84",
    "crs_confidence": 87.5,
    "is_inside_nigeria": true,
    "area_discrepancy_pct": null,
    "warnings": []
  },

  "terrain_assessment": {
    "elevation_m": 12.4,
    "steepness_of_land": 3.1,
    "terrain_difficulty": "gentle",
    "suitability": "SUITABLE"
  },

  "flood_risk_metrics": {
    "level": "LOW",
    "score": 0.28,
    "reason_in_plain_english": "string",
    "distance_to_nearest_river": 820,
    "water_presence_index": 0.08
  },

  "accessibility_development": {
    "distance_to_road_m": 340,
    "road_category": "Good",
    "suitability_matrix": {
      "residential": true,
      "commercial": false,
      "agricultural": true,
      "industrial": false
    }
  },

  "encroachment": {
    "flag": false,
    "detail": "No new structures detected in 200m buffer (2020–2024)",
    "satellite_epoch_comparison": "2020 vs 2024"
  },

  "growth_potential": {
    "level": "MEDIUM",
    "urban_expansion_score": 0.54,
    "infrastructure_proximity": {
      "road_km": 0.34,
      "airport_km": 12.1,
      "rail_km": null
    },
    "summary_notes": "string"
  },

  "advisory_flags": [],

  "summary": {
    "traffic_light": "GREEN",
    "executive_summary": "3 sentences maximum. One clear risk statement per sentence. Humanized, direct, plain English tone.",
    "ai_recommendation": "Empathetic, clear, advisory text block. Ends with: This report is advisory. Engage a SURCON-registered surveyor and a qualified property lawyer before committing any funds.",
    "overall_risk_score": 28.0
  }
}
```

> [!NOTE]
> **v2.0 Schema Field Changes from v1.0** (for developer reference):
> - `parcel` → `parcel_geometry` · LGA/state/community nested under `location_context`
> - `terrain.slope_pct` → `terrain_assessment.steepness_of_land` (user-facing label)
> - `flood_risk.reason` → `flood_risk_metrics.reason_in_plain_english`
> - `flood_risk.distance_to_river_m` → `flood_risk_metrics.distance_to_nearest_river`
> - `flood_risk.ndwi` → `flood_risk_metrics.water_presence_index`
> - `accessibility` → `accessibility_development` · `development_suitability` merged into `suitability_matrix`
> - `growth_potential.notes` → `growth_potential.summary_notes`

---

## 14. Agent Failure Handling

If any sub-agent returns an error or `null` for a critical field:
- **Do not** propagate null silently
- Add to `advisory_flags`: `"[FIELD_NAME]: Data unavailable. Manual check required."`
- Reduce the report's effective `data_confidence` rating
- **Never** block the full report for one missing non-critical indicator
- **Exception:** Coordinates must fully resolve before any downstream agent runs. The pipeline cannot start without a valid, user-confirmed parcel polygon.
- ReportGen must reference every `[LOW DATA]` or `[UNAVAILABLE]` field in the executive summary

---

## 15. Technology Stack (Unified · Local-First · Zero Cloud LLM)

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | Next.js 14 + Tailwind CSS | SSR, fast map rendering |
| **Map** | Leaflet + OSM tiles | Free, no API key, local-compatible |
| **Backend API** | FastAPI (Python) | Async, native GIS library support |
| **LLM Orchestrator** | **Ollama (llama3 / mistral) — LOCAL** | Zero cloud calls · data privacy · zero API cost |
| **Tool Interface** | MCP JSON-RPC pattern | Atomic tool encapsulation |
| **OCR / Coord Extract** | Tesseract + regex (Python) | Local, no Google Vision API |
| **GIS Processing** | GeoPandas + Shapely + GDAL | Polygon ops, CRS transforms, buffer analysis |
| **CRS Transform** | pyproj | Minna Datum → WGS84, UTM → WGS84 |
| **Schema Validation** | Pydantic (Python) | Enforced at every agent boundary |
| **Elevation Data** | SRTM 30m — local offline tiles or AWS Terrain Tiles | Free, 30m resolution |
| **Hydrology** | HydroSHEDS (HydroRIVERS) | River network, Strahler order |
| **Roads / POI** | OpenStreetMap via Overpass API | Free, community-maintained |
| **Satellite Imagery** | Sentinel-2 (SentinelHub or GEE) | Free 10m, multi-temporal |
| **Spatial DB** | PostgreSQL + PostGIS | Spatial queries, parcel storage |
| **Session State DB** | SQLite | Lightweight, local session partitioning |
| **Job Queue** | Celery + Redis | Async GIS jobs, 5-min SLA |
| **PDF Generation** | WeasyPrint | HTML template → branded PDF |
| **Auth** | Supabase Auth | Email/OTP, JWT, row-level security |
| **Payments** | Paystack | NGN payments, webhooks |
| **Hosting** | Railway / Render (backend) + Vercel (frontend) | No DevOps overhead at MVP |
| **File Storage** | Supabase Storage / AWS S3 | Uploads + generated PDFs |

---

## 16. End-to-End System Flow

| Step | Actor | Action | Output / Guard |
|---|---|---|---|
| 1 | User | Signs up / logs in via OTP email | JWT token issued |
| 2 | User | Uploads survey plan PDF, coordinates, KML, or shapefile | File stored to S3. Job queued. |
| 3 | **Sanitization Filter** | Scans input for injection patterns | Clean → proceed. Hazard → halt + notify. |
| 4 | **CoordExtract (Python + MCP)** | Tesseract OCR + CRS heuristics + auto-flip test | Coordinate array + CRS + confidence score + `run_id` |
| 5 | System | CRS dialog if `crs_confidence < 60` | User confirms CRS |
| 6 | System | Parcel plotted on Leaflet map. *"Is this your land?"* | User clicks YES or edits |
| 7 | System | Nigeria bbox check + area discrepancy check | Dialogs T1–T5 fired as needed |
| 8 | **GISAnalysis (Python + MCP)** | DEM + hydrology + OSM + Sentinel-2 | GIS output JSON — all indicators |
| 9 | **RiskAssess (Python)** | Deterministic rule engine | Risk levels + confidence scores |
| 10 | **SuitabilityGrowth (Python + MCP)** | OSM density rings + infrastructure proximity | Growth score + conflict flags |
| 11 | **ReportGen (Python + Ollama)** | Python fills schema → Ollama writes text fields | Full JSON report |
| 12 | **Output Scrubber** | Erases paths, ports, debug vars | Clean payload |
| 13 | **Pydantic Validation** | Final schema enforcement | Validated JSON |
| 14 | System | WeasyPrint renders HTML → PDF + map screenshot | Branded PDF |
| 15 | User | Downloads PDF / shares link / saves to dashboard | Report stored in account |

---

## 17. MVP Build Sequence — 4-Week Sprint

> [!IMPORTANT]
> Build in this exact order. Each week produces a working, testable increment. Do not jump to Week 3 without Week 1 validated with real paying users.

| Week | Focus | Deliverable | Success Metric |
|---|---|---|---|
| **Week 1** | Sanitization Gate + Coordinate Validator + Map Preview | Input scrubber → coordinate extraction → Leaflet polygon → CRS dialog → "Is this your land?" → YES gate | 5 surveyors test it. Zero silent coordinate errors. Zero prompt injection bypasses. |
| **Week 2** | Flood + Terrain Analysis | Confirmed parcel → SRTM elevation + slope + HydroSHEDS → flood risk classification → terrain suitability | Risk classification matches manual surveyor check on 10 test parcels from the golden dataset |
| **Week 3** | Accessibility + Encroachment + PDF | OSM road distance + Sentinel-2 epoch comparison + WeasyPrint PDF | Full report generated in <5 minutes. PDF downloadable and shareable. |
| **Week 4** | Paystack + Dashboard + 10 Paying Users | ₦3,000/report payment flow + report history dashboard + circuit breakers active | 10 paying transactions. ₦30,000+ revenue. Golden dataset eval passing at 100%. |

---

## 18. Product Risk Guardrails

| Risk | System Mitigation | Prohibited Output |
|---|---|---|
| Wrong flood score causes buyer loss | `data_confidence` shown on every indicator. `[LOW DATA]` flag below 50. `null` below 30. | Never say *"No flood risk"* |
| Implied legal title verification | Mandatory disclaimer on every PDF page. No C of O or registry claims. | Never output *"Title is clear"* |
| Government acquisition false negative | Advisory framing only. Direct user to Surveyor-General. | Never output *"No government acquisition risk"* |
| CRS error produces wrong polygon | Auto-flip test + mandatory map preview + user confirmation gate | Analysis cannot run without confirmed map visualisation |
| LLM hallucinating risk scores | Python fills all numeric fields before LLM call. LLM writes text only. | Never let Ollama set a risk level or boolean flag |
| Prompt injection compromise | Step 0 sanitization filter runs before any parsing | Any injection attempt → `[EXECUTION_HAZARD]` halt |
| Infinite LLM execution loop | 3-call circuit breaker in host loop | Trigger `[SYSTEM_INF_LOOP]` → step down to human triage |
| Private data leaked in output | Output leak scrubber strips paths, ports, secrets before delivery | No file paths or DB credentials in any response |

---

## 19. Revenue Architecture

| Tier | Price | Included | Target User |
|---|---|---|---|
| Free | ₦0 — 1 report/month | Full physical risk report, PDF, map preview | Land buyers testing the product |
| Pay-Per-Report | ₦3,000–₦5,000/report | Full report on demand | Occasional buyers, one-off surveyors |
| Starter | ₦10,000/month — 5 reports | Dashboard, watermark-free PDF | Independent realtors, small surveyors |
| Professional | ₦30,000/month — 20 reports | Bulk analysis, white-label PDF, API access | Surveying firms, developer site screening |
| Enterprise | Custom (₦500k+/year) | Unlimited reports, custom data layers, SLA | Banks, government agencies, large developers |

---

## 20. The Sovereign Architectural Commandment

> **If a user's coordinate stream plots outside the spatial boundary of Nigeria and the processing layers detect it before the expensive analytical runs trigger — that instant validation event is your primary value proposition.**
>
> Be perfectly honest about what your data layers know, and explicitly communicative about what they do not.
>
> **Earning and preserving user trust overrides all structural features. Build trust first. Everything else is downstream of trust.**

---

## 21. Open Questions for Stakeholder Decision

> [!IMPORTANT]
> **Sentinel-2 Access:** SentinelHub and Google Earth Engine are cloud services. For strict zero-cloud MVP, substitute with pre-downloaded Sentinel-2 tiles for key Nigerian urban zones? Or accept satellite imagery as the single permitted cloud dependency?

> [!IMPORTANT]
> **Ollama Model Tag:** For a 16 GB RAM machine, `llama3:8b` (4-bit quantised, ~5 GB) is recommended. Confirm or specify a different model tag before Week 1 begins.

> [!IMPORTANT]
> **Tesseract Quality Floor:** Tesseract is significantly less accurate on degraded Nigerian survey plan scans (handwritten annotations, low-resolution photocopies). Accept a Google Vision API fallback path for OCR only, or remain fully local and invest in Tesseract fine-tuning on Nigerian survey plan samples?

> [!NOTE]
> **Government Gazette Data:** No government registry data is accessible at MVP. OSM + open data only. The system outputs *"No acquisition signals in available open data"* — never *"No acquisition risk."* This is the correct and only legal posture.

---

*— End of LandIQ Unified Operational Plan v2.0 —*
