import { createPortal } from "react-dom";
import { useState, useRef, useEffect } from "react";
import { useLocation } from "wouter";
import {
  Check, X, ChevronDown, ChevronUp, RefreshCw, Table2, Loader2, AlertTriangle, MapPin, Pencil
} from "lucide-react";
import { useAppContext } from "@/context/AppContext";
import { useToast } from "@/hooks/use-toast";
import { apiUrl } from "@/lib/api";

// ─── Sub-components — all use CSS theme variables (dark + light safe) ─────────

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4">
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-3">
      {children}
    </p>
  );
}

function HealthRow({ label, value, ok = true }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border/60 last:border-0">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className={`flex items-center gap-1.5 text-sm font-semibold ${ok ? "text-emerald-500" : "text-amber-400"}`}>
        <Check className="w-3.5 h-3.5" strokeWidth={3} />
        {value}
      </span>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold mb-0.5">
        {label}
      </p>
      <p className="text-foreground text-sm font-medium">{value}</p>
    </div>
  );
}

function AreaRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex justify-between items-baseline gap-4">
      <span className="text-muted-foreground text-sm flex-shrink-0">{label}</span>
      <span className="text-foreground text-sm font-medium text-right">
        {value}
        {sub && <span className="text-muted-foreground text-xs ml-1 block">{sub}</span>}
      </span>
    </div>
  );
}

function WarningBox({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2.5 p-3 mt-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400">
      <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
      <p className="text-xs font-medium leading-relaxed">{message}</p>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function GatePanel() {
  const [, setLocation] = useLocation();
  const { analysisState, setAnalysisState, sessionId, setParcelCoords } = useAppContext();
  const { toast } = useToast();

  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [reprojecting, setReprojecting] = useState(false);
  const [showZoneSelector, setShowZoneSelector] = useState(false);
  const [selectedCrs, setSelectedCrs] = useState<string>("EPSG:26332");
  const [isConfirming, setIsConfirming] = useState(false);
  // F2: pipeline stage for progress indicator during report generation
  const [pipelineStage, setPipelineStage] = useState<string>("");
  // P1: poll fallback interval ref — cancelled when SSE delivers report
  const pollFallbackRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sessionData, setSessionData] = useState<any>(null);
  const [loading, setLoading] = useState(!!sessionId);
  const [viaStatus, setViaStatus] = useState<string>("idle");

  const CRS_OPTIONS = [
    {
      code: "EPSG:26332",
      badgeColor: "bg-emerald-500",
      label: "Central & South-East (Zone 32N)",
      sub: "Uyo, Port Harcourt, Abuja, Enugu, Kano, Edo, Rivers",
    },
    {
      code: "EPSG:26331",
      badgeColor: "bg-blue-500",
      label: "Western Nigeria (Zone 31N)",
      sub: "Lagos, Ogun, Oyo, Osun, Ondo, Ekiti, Kwara",
    },
    {
      code: "EPSG:26333",
      badgeColor: "bg-amber-500",
      label: "Far East & Northeast (Zone 33N)",
      sub: "Borno (Maiduguri), Yobe, Adamawa, Taraba",
    },
    {
      code: "EPSG:32632",
      badgeColor: "bg-slate-400",
      label: "Modern GPS / Google Earth (WGS84)",
      sub: "Direct handheld GPS lat/long or WGS84 UTM",
    },
  ];

  const handleZoneReproject = async (newEpsg: string) => {
    if (!sessionId) return;
    setSelectedCrs(newEpsg);
    setShowZoneSelector(false);
    setReprojecting(true);
    toast({ title: "Reprojecting map...", description: `Applying ${newEpsg} transformation` });
    try {
      const res = await fetch(apiUrl(`/api/session/${sessionId}/reproject`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ epsg_code: newEpsg }),
      });
      if (res.ok) {
        const data = await res.json();
        const wgs84 = data.wgs84_polygon || data.coordinates_wgs84 || null;
        if (wgs84 && Array.isArray(wgs84) && wgs84.length > 0) {
          setParcelCoords(wgs84.map((pt: number[]) => [pt[0], pt[1]] as [number, number]));
        }
        toast({ title: "Reprojection complete", description: `Boundary re-anchored using ${newEpsg}` });
      }
    } catch {
      toast({ title: "Reprojection error", variant: "destructive" });
    } finally {
      setReprojecting(false);
    }
  };

  // Read LLM config from localStorage (set by AnalysePanel advanced settings)
  const llmProvider = localStorage.getItem("landiq_llm_provider") || "";
  const llmApiKey   = localStorage.getItem("landiq_llm_api_key") || "";
  const llmGrounding = localStorage.getItem("landiq_llm_grounding") || "";

  // Poll VIA background processing status
  useEffect(() => {
    if (!sessionId) return;
    const checkVia = () => {
      fetch(apiUrl(`/api/via/status/${sessionId}`))
        .then(r => r.json())
        .then(data => {
          if (data?.status) setViaStatus(data.status);
        })
        .catch(() => {});
    };
    checkVia();
    const interval = setInterval(checkVia, 3000);
    return () => clearInterval(interval);
  }, [sessionId]);

  // Fetch session data when sessionId arrives — with 10s timeout guard
  useEffect(() => {
    if (!sessionId) { setLoading(false); return; }
    setLoading(true);

    // 10-second timeout: if data never arrives, show unavailable state
    const timeout = setTimeout(() => {
      setLoading(false);
    }, 10_000);

    fetch(apiUrl(`/api/session/${sessionId}`))
      .then(r => r.json())
      .then(data => {
        clearTimeout(timeout);
        setSessionData(data);

        // Push WGS84 polygon into AppContext so the map can draw it
        const wgs84 =
          data.coord_extract?.wgs84_polygon ||
          data.coord_extract?.coordinates_wgs84 ||
          null;
        if (wgs84 && Array.isArray(wgs84) && wgs84.length > 0) {
          setParcelCoords(wgs84.map((pt: number[]) => [pt[0], pt[1]] as [number, number]));
        }

        setLoading(false);
      })
      .catch(() => {
        clearTimeout(timeout);
        setLoading(false);
      });

    return () => clearTimeout(timeout);
  }, [sessionId, setParcelCoords]);

  // ── Confirm ─────────────────────────────────────────────────────────────────
  // P1: Poll fallback — if SSE stream drops, still navigate to report
  const startPollFallback = (runId: string) => {
    if (pollFallbackRef.current) clearInterval(pollFallbackRef.current);
    pollFallbackRef.current = setInterval(async () => {
      try {
        const r = await fetch(apiUrl(`/api/session/${runId}`));
        const sess = await r.json();
        if (sess?.pipeline_stage === "COMPLETE" || sess?.status === "complete") {
          if (pollFallbackRef.current) clearInterval(pollFallbackRef.current);
          setAnalysisState("complete");
          setLocation("/report");
        }
      } catch { /* silent — SSE may still be active */ }
    }, 5000);
  };

  const handleConfirm = async () => {
    if (!sessionId) {
      toast({ title: "Error", description: "No active session.", variant: "destructive" });
      return;
    }
    setIsConfirming(true);
    setPipelineStage("geospatial"); // F2: show first stage immediately
    toast({ title: "Confirming…", description: "Triggering spatial analysis." });
    try {
      const res = await fetch(apiUrl(`/api/confirm/${sessionId}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          responses: {},
          ...(llmProvider  && { llm_provider:  llmProvider }),
          ...(llmApiKey    && { llm_api_key:   llmApiKey }),
          ...(llmGrounding && { llm_grounding: llmGrounding }),
        }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        const errMsg = errorData?.detail?.message || errorData?.detail?.instruction || errorData?.detail || errorData?.message || "Confirm failed";
        throw new Error(typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg));
      }

      // P1: Start SSE stream for live stage updates
      const sse = new EventSource(apiUrl(`/api/stream/${sessionId}`));

      // F2: update stage label as pipeline progresses
      sse.addEventListener("stage_progress", (e: MessageEvent) => {
        try { setPipelineStage(JSON.parse(e.data)?.stage ?? ""); } catch { /* ignore */ }
      });
      sse.addEventListener("risk_summary",   () => setPipelineStage("risk_summary"));
      sse.addEventListener("report_started", () => setPipelineStage("report_gen"));

      sse.addEventListener("report_complete", () => {
        sse.close();
        if (pollFallbackRef.current) clearInterval(pollFallbackRef.current);
        setPipelineStage("");
        setAnalysisState("complete");
        setLocation("/report");
      });

      sse.onerror = () => {
        // P1: SSE dropped — polling fallback keeps us alive
        sse.close();
      };

      // P1: Start 5s polling as a safety net in case SSE never fires report_complete
      startPollFallback(sessionId);

      toast({ title: "Analysis confirmed", description: "Generating your spatial report…" });

    } catch (e: any) {
      setPipelineStage("");
      toast({ title: "Error", description: e.message, variant: "destructive" });
    } finally {
      setIsConfirming(false);
    }
  };

  // ── Reject ─────────────────────────────────────────────────────────────────
  const handleReject = async () => {
    if (sessionId) {
      await fetch(apiUrl(`/api/reject/${sessionId}`), { method: "POST" }).catch(() => {});
    }
    toast({
      title: "Analysis rejected",
      description: "Please re-upload or adjust your coordinates.",
      variant: "destructive",
    });
    setAnalysisState(null);
    setParcelCoords(null);
    setLocation("/analyse");
  };

  // ── Recompute — wired to /api/preview/{id} ─────────────────────────────────
  const handleRecompute = async () => {
    if (!sessionId) return;
    setRecomputing(true);
    toast({ title: "Recomputing polygon boundaries…" });
    try {
      const res = await fetch(apiUrl(`/api/preview/${sessionId}`));
      if (res.ok) {
        const data = await res.json();
        const wgs84 = data.wgs84_polygon || data.coordinates_wgs84 || null;
        if (wgs84) setParcelCoords(wgs84.map((pt: number[]) => [pt[0], pt[1]] as [number, number]));
        toast({ title: "Recompute complete", description: "Polygon updated." });
      } else {
        toast({ title: "Recompute failed", variant: "destructive" });
      }
    } catch {
      toast({ title: "Recompute error", variant: "destructive" });
    } finally {
      setRecomputing(false);
    }
  };

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-muted-foreground p-5 text-center bg-card">
        <Loader2 className="w-8 h-8 animate-spin mb-4 text-primary" />
        <p className="text-sm">Loading coordinate extraction results…</p>
      </div>
    );
  }

  // ── Derived display values ─────────────────────────────────────────────────
  const ext = sessionData?.coord_extract || {};
  const computedSqm = ext.computed_area_ha ? ext.computed_area_ha * 10000 : (ext.polygon?.computed_area_sqm || 0);
  const statedSqm   = ext.stated_area_ha   ? ext.stated_area_ha   * 10000 : (ext.polygon?.stated_area_sqm || null);
  const isMinna = (ext.detected_crs || ext.crs_input || "").includes("MINNA");
  const plotSqm = 648; // Lagos default
  const discrepancy = ext.area_discrepancy_pct ?? ext.polygon?.area_discrepancy_pct ?? null;
  const closureErr = ext.polygon?.closure_error_m ?? ext.health_check_stats?.closure_error_m ?? null;
  const hasSelfInt = ext.polygon?.has_self_intersection ?? false;

  const hasBeacons = ext.beacons && ext.beacons.length > 0;
  const ledgerData = hasBeacons 
    ? ext.beacons.map((b: any) => ({
        id: b.station_id,
        col1: (b.easting_utm ?? b.easting ?? 0).toFixed(3),
        col2: (b.northing_utm ?? b.northing ?? 0).toFixed(3),
        lat: b.wgs84_lat ? b.wgs84_lat.toFixed(6) : "--",
        lng: b.wgs84_lng ? b.wgs84_lng.toFixed(6) : "--",
        source: b.source || "Extracted",
      }))
    : (ext.coordinates || []).map((pt: number[], i: number) => ({
        id: i === (ext.coordinates?.length ?? 0) - 1 ? "S1(close)" : `S${i + 1}`,
        col1: isMinna ? pt[0].toFixed(3) : pt[0].toFixed(6),
        col2: isMinna ? pt[1].toFixed(3) : pt[1].toFixed(6),
        lat: "--",
        lng: "--",
        source: "Extracted",
      }));

  // F2: Stage labels shown while report is generating after confirm
  const PIPELINE_STAGES: Record<string, { label: string; pct: number }> = {
    geospatial:  { label: "Fetching satellite & flood data…", pct: 30 },
    risk_summary: { label: "Computing risk scores…",          pct: 60 },
    report_gen:  { label: "Writing your report…",             pct: 85 },
  };
  const stageInfo = pipelineStage ? PIPELINE_STAGES[pipelineStage] : null;

  return (
    <div className="flex flex-col h-full bg-background text-foreground">

      {/* F2: Report generation progress overlay (Portaled to center over entire screen) */}
      {stageInfo && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm px-4 animate-in fade-in duration-300">
          <div className="bg-background border border-border/60 rounded-2xl p-6 shadow-2xl w-full max-w-sm space-y-5 animate-in zoom-in-95 duration-300">
            <div className="flex items-center justify-center">
              <div className="w-14 h-14 bg-primary/10 rounded-full flex items-center justify-center">
                <Loader2 className="w-7 h-7 text-primary animate-spin" />
              </div>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-foreground">{stageInfo.label}</p>
                <p className="text-sm font-bold text-primary tabular-nums">{stageInfo.pct}%</p>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${stageInfo.pct}%` }}
                />
              </div>
              <div className="flex gap-2 justify-center pt-1">
                {["geospatial","risk_summary","report_gen"].map(s => (
                  <div
                    key={s}
                    className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${
                      Object.keys(PIPELINE_STAGES).indexOf(s) <=
                      Object.keys(PIPELINE_STAGES).indexOf(pipelineStage)
                        ? "bg-primary"
                        : "bg-muted"
                    }`}
                  />
                ))}
              </div>
              <p className="text-xs text-center text-muted-foreground">
                This takes 30–90 seconds. Do not close this tab.
              </p>
            </div>
          </div>
        </div>,
        document.body
      )}
      {/* ── Header ── */}
      <div className="px-5 pt-6 pb-4 flex-shrink-0 border-b border-border">
        <h2 className="text-xl font-bold tracking-tight text-foreground mb-1">
          Verify Extraction
        </h2>
        <p className="text-muted-foreground text-xs leading-relaxed">
          Please confirm the detected geometry is accurate before the analytical run.
        </p>
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">

        {/* ── Active CRS & Location Status Pill (Non-Blocking) ── */}
        <div className="bg-primary/5 border border-primary/20 rounded-2xl p-3.5 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <MapPin className="w-3.5 h-3.5 text-primary flex-shrink-0" />
              <span className="text-xs font-semibold text-foreground truncate">
                Plotted in: <span className="font-bold text-primary">{ext.detected_crs || ext.crs_input || selectedCrs}</span>
              </span>
            </div>
            <button
              onClick={() => setShowZoneSelector(v => !v)}
              disabled={reprojecting}
              className="text-xs font-bold text-primary hover:underline flex items-center gap-1.5 bg-primary/10 hover:bg-primary/20 px-2.5 py-1 rounded-full transition-all flex-shrink-0 disabled:opacity-50"
            >
              {reprojecting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Pencil className="w-3 h-3" />}
              {showZoneSelector ? "Close" : "Switch Zone"}
            </button>
          </div>

          {showZoneSelector && (
            <div className="mt-3 pt-3 border-t border-primary/15 space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Select State / Regional CRS (1-Click Realtime Reprojection)
              </p>
              <div className="grid grid-cols-1 gap-1.5 text-xs">
                {CRS_OPTIONS.map(opt => (
                  <button
                    key={opt.code}
                    onClick={() => handleZoneReproject(opt.code)}
                    className={`flex items-center justify-between p-2.5 rounded-xl text-left transition-all ${
                      (ext.detected_crs || ext.crs_input || selectedCrs) === opt.code
                        ? "bg-primary text-primary-foreground font-bold shadow"
                        : "bg-card hover:bg-muted text-foreground border border-border"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <span className={`w-2.5 h-2.5 rounded-full ${opt.badgeColor} flex-shrink-0 mt-1`} />
                      <div>
                        <div className="font-semibold">{opt.label}</div>
                        <div className="text-[10px] opacity-80">{opt.sub}</div>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono opacity-70 ml-2 flex-shrink-0">{opt.code}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Plan Metadata */}
        <SectionCard>
          <SectionLabel>Plan Metadata</SectionLabel>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <MetaRow label="Location" value={`${ext.lga || ext.plan_details?.location || "Unknown"}, ${ext.state || "Nigeria"}`} />
            <MetaRow label="Datum" value={ext.detected_crs || ext.crs_input || "UTM Zone 32N"} />
            <MetaRow label="Owner" value={ext.plan_details?.owner_name || "Unknown"} />
            <MetaRow label="Plan No" value={ext.plan_details?.plan_number || "Unknown"} />
          </div>
        </SectionCard>

        {/* Coordinate Health Check */}
        <SectionCard>
          <SectionLabel>Coordinate Health Check</SectionLabel>
          <HealthRow label="Closed Polygon" value={ext.health_check_stats?.is_closed ?? ext.polygon?.is_closed ? "Yes" : "Auto-Closed"} />
          {closureErr != null && (
            <HealthRow label="Closure Error" value={`${closureErr.toFixed(2)}m`} ok={closureErr <= 0.5} />
          )}
          <HealthRow label="Beacon Count"   value={`${ext.coordinates?.length ?? ext.beacons?.length ?? 0} beacons`} />
          <HealthRow
            label="Self-Intersection"
            value={hasSelfInt ? "Intersecting" : "Passed"}
            ok={!hasSelfInt}
          />
          {hasSelfInt && (
            <div className="mt-2 flex justify-end">
              <button
                onClick={handleRecompute}
                disabled={recomputing}
                className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
              >
                <RefreshCw className={`w-3 h-3 ${recomputing ? "animate-spin" : ""}`} />
                {recomputing ? "Fixing..." : "Attempt Auto-Fix"}
              </button>
            </div>
          )}
          <HealthRow
            label="Satellite Visual Scan"
            value={
              viaStatus === "complete" ? "Scan Complete" :
              viaStatus === "pending" || viaStatus === "triggering" ? "Analyzing in background…" :
              viaStatus === "low_quality" ? "Low Imagery Clarity" : "Queued"
            }
            ok={viaStatus === "complete"}
          />
        </SectionCard>

        {/* Area Verification */}
        <SectionCard>
          <SectionLabel>Area Verification</SectionLabel>
          <div className="space-y-2.5">
            <AreaRow
              label="Stated Area"
              value={statedSqm ? `${statedSqm.toLocaleString(undefined, { maximumFractionDigits: 0 })} sqm` : "Not stated"}
            />
            <AreaRow
              label="Computed Area"
              value={`${computedSqm.toLocaleString(undefined, { maximumFractionDigits: 0 })} sqm`}
              sub={`≈ ${(computedSqm / plotSqm).toFixed(1)} plots · ${(computedSqm / 10000).toFixed(2)} ha`}
            />
            <div className="flex justify-between items-center pt-1 border-t border-border/40">
              <span className="text-muted-foreground text-sm">Discrepancy</span>
              {discrepancy != null ? (
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                  discrepancy <= 3 ? "bg-emerald-500/15 text-emerald-500" :
                  discrepancy <= 10 ? "bg-amber-500/15 text-amber-500" :
                  "bg-red-500/15 text-red-500"
                }`}>
                  {discrepancy.toFixed(1)}%
                </span>
              ) : (
                <span className="text-muted-foreground text-sm">--</span>
              )}
            </div>
            {(ext.polygon?.perimeter_display || ext.perimeter_display) && (
              <AreaRow
                label="Perimeter"
                value={ext.polygon?.perimeter_display || ext.perimeter_display}
              />
            )}
          </div>
          {discrepancy != null && Math.abs(discrepancy) > 5 && (
            <WarningBox message={`Area discrepancy of ${discrepancy.toFixed(1)}% exceeds the 5% acceptable threshold.`} />
          )}
        </SectionCard>

        {/* Ledger toggle */}
        <button
          onClick={() => setLedgerOpen(v => !v)}
          className="w-full flex items-center justify-between bg-card rounded-2xl border border-border px-4 py-3.5 text-left hover:border-primary/40 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <Table2 className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground">Review Technical Details (Ledger)</span>
          </div>
          {ledgerOpen
            ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
            : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </button>

        {/* Coordinate Ledger Table */}
        {ledgerOpen && (
          <div className="bg-muted/30 rounded-2xl border border-border overflow-hidden">
            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest px-4 pt-3 pb-2">
              Coordinate Ledger
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[360px]">
                <thead>
                  <tr className="border-b border-border">
                    {[
                      "Station ID",
                      (hasBeacons || isMinna) ? "Easting (m)" : "Latitude",
                      (hasBeacons || isMinna) ? "Northing (m)" : "Longitude",
                      "Source",
                    ].map(h => (
                      <th key={h} className="text-left px-4 py-2 text-[9px] font-bold text-muted-foreground uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ledgerData.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-3 text-xs text-muted-foreground text-center">
                        No coordinates extracted
                      </td>
                    </tr>
                  ) : ledgerData.map((row: any, i: number) => (
                    <tr key={i} className="border-b border-border/40 last:border-0">
                      <td className="px-4 py-2.5 text-xs font-mono text-primary">{row.id}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-foreground">{row.col1}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-foreground">{row.col2}</td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{row.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {ext.health_check_stats && !ext.health_check_stats.is_closed && (
              <div className="px-4 py-3 bg-amber-500/10 border-t border-amber-500/20 flex items-center gap-2 text-amber-600 dark:text-amber-400">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <p className="text-[10px] uppercase font-bold tracking-wider">Partial extraction detected. Ensure polygon is closed.</p>
              </div>
            )}
          </div>
        )}

        {/* Recompute — wired to /api/preview */}
        {analysisState !== "complete" && (
          <button
            onClick={handleRecompute}
            disabled={recomputing}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl border border-primary/40 bg-primary/10 text-primary text-sm font-semibold hover:bg-primary/20 transition-all disabled:opacity-60"
          >
            <RefreshCw className={`w-4 h-4 ${recomputing ? "animate-spin" : ""}`} />
            {recomputing ? "Recomputing…" : "Recompute Polygon"}
          </button>
        )}
      </div>

      {/* ── Sticky footer: Reject / Confirm ── */}
      {analysisState !== "complete" && (
        <div className="flex-shrink-0 px-4 pt-3 pb-[calc(env(safe-area-inset-bottom,0px)+16px)] lg:pb-6 border-t border-border bg-background flex gap-3">
          <button
            onClick={handleReject}
            className="flex-1 h-12 rounded-full border border-destructive/40 bg-destructive/8 text-destructive text-sm font-bold flex items-center justify-center gap-2 hover:bg-destructive/15 transition-all active:scale-[0.98]"
          >
            <X className="w-4 h-4" strokeWidth={2.5} /> Reject
          </button>
          <button
            onClick={handleConfirm}
            disabled={isConfirming}
            className="flex-1 h-12 rounded-full bg-primary text-primary-foreground text-sm font-bold flex items-center justify-center gap-2 hover:bg-primary/90 shadow-lg transition-all active:scale-[0.98] disabled:opacity-70"
          >
            {isConfirming
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Check className="w-4 h-4" strokeWidth={2.5} />}
            {isConfirming ? "Confirming…" : "Confirm"}
          </button>
        </div>
      )}
    </div>
  );
}
