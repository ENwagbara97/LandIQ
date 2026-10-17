import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { Download, FolderPlus, Info, TrendingUp, Droplets, Leaf, Mountain, MapPin, Loader2, ExternalLink, Printer, Share2, FileText, Route, Building2, AlertTriangle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip as ReTooltip } from "recharts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAppContext } from "@/context/AppContext";
import { cn } from "@/lib/utils";
import { PrintAdjustmentModal } from "./PrintAdjustmentModal";
import { TopographicAssessmentSection } from "./TopographicAssessmentSection";
import { VIAScanCard } from "./VIAScanCard";
import { NearbyLandmarksCard } from "./NearbyLandmarksCard";
import { NewsAlertsWidget } from "./NewsAlertsWidget";
import { SiteNavigationPanel } from "../navigation/SiteNavigationPanel";
import { Navigation } from "lucide-react";
import { useReportStream } from "@/hooks/useReportStream";
import { usePdfStatus } from "@/hooks/usePdfStatus";
import { MetricCardSkeleton, TrafficLightSkeleton, ExecutiveSummarySkeleton } from "../skeletons/MetricCardSkeleton";

import { apiUrl } from "@/lib/api";

function _buildElevationTransect(geeData: any) {
  if (!geeData?.grid || !Array.isArray(geeData.grid) || geeData.grid.length === 0) return null;
  const grid = geeData.grid;
  const scale = geeData.scale_m || 30;
  const numRows = grid.length;
  const numCols = grid[0]?.length || 0;
  if (numRows === 0 || numCols === 0) return null;

  const steps = Math.max(numRows, numCols);
  const points = [];
  for (let i = 0; i < steps; i++) {
    const r = Math.min(Math.floor((i / (steps - 1 || 1)) * (numRows - 1)), numRows - 1);
    const c = Math.min(Math.floor((i / (steps - 1 || 1)) * (numCols - 1)), numCols - 1);
    const elev = grid[r]?.[c];
    const distM = Math.round(i * scale * Math.sqrt(2));
    if (typeof elev === "number" && !isNaN(elev)) {
      points.push({ d: `${distM}m`, elevation: Math.round(elev * 10) / 10 });
    }
  }
  return points.length > 1 ? points : null;
}

const metrics = [
  {
    icon: Mountain, label: "Elevation", color: "text-slate-500 dark:text-slate-300",
    key: "elevation",
    tip: "Height above mean sea level at the parcel centroid.",
  },
  {
    icon: TrendingUp, label: "Slope", color: "text-blue-500",
    key: "slope",
    tip: "Average terrain gradient across the parcel. <5° is generally buildable.",
  },
  {
    icon: Droplets, label: "Flood Risk", color: "text-sky-500",
    key: "floodRisk",
    tip: "Probability of 1-in-100-year flood event based on elevation and drainage models.",
  },
  {
    icon: Leaf, label: "Veg Density", color: "text-emerald-500",
    key: "vegDensity",
    tip: "NDVI-derived vegetation cover percentage from latest Sentinel-2 imagery.",
  },
  {
    icon: Route, label: "Nearest Road", color: "text-orange-500",
    key: "roadDist",
    tip: "Distance to the nearest documented road/street network.",
  },
  {
    icon: Building2, label: "Growth Potential", color: "text-purple-500",
    key: "growth",
    tip: "Calculated from OSM urban density and infrastructure proximity.",
  },
];

export function ReportPanel() {
  const [, setLocation] = useLocation();
  const { reportData, setReportData, sessionId, mapViewport, parcelCoords, selectedLotId, setSelectedLotId } = useAppContext();
  const { toast } = useToast();
  const [reportType, setReportType] = useState<"simple" | "expert">("simple");
  const [loading, setLoading] = useState(true);
  // Data sources are shown only in the PDF — not in the UI
  const [exportingPDF, setExportingPDF] = useState(false);
  const [exportingPNG, setExportingPNG] = useState(false);
  const [showPrintModal, setShowPrintModal] = useState(false);
  const [exportFormat, setExportFormat] = useState<"pdf" | "png">("pdf");
  const [geeElevation, setGeeElevation] = useState<any>(null);

  // Fetch real GEE elevation grid if available for the report
  useEffect(() => {
    if (!sessionId) return;
    fetch(apiUrl(`/api/report/${sessionId}/gee-elevation`))
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.elevation_available !== false) {
          setGeeElevation(data);
        }
      })
      .catch(() => {});
  }, [sessionId]);

  const [tappedMetric, setTappedMetric] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const [showNav, setShowNav] = useState(false);
  const [navData, setNavData] = useState<any>(null);
  const [loadingNav, setLoadingNav] = useState(false);

  const handleNavigateClick = async () => {
    if (!sessionId) return;
    setLoadingNav(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/reports/${sessionId}/navigation-data`);
      if (res.ok) {
        const data = await res.json();
        setNavData(data);
        setShowNav(true);
      } else {
        toast({ title: "Navigation Unavailable", description: "Could not load routing data.", variant: "destructive" });
      }
    } catch (e) {
      toast({ title: "Navigation Failed", description: "Network error.", variant: "destructive" });
    } finally {
      setLoadingNav(false);
    }
  };

  const isHistoricalReport = !!(reportData as any)?.generated_at;
  const { sections, stage, complete, error: streamError, errorMessage: streamErrorMessage } = useReportStream(isHistoricalReport ? null : sessionId);
  const { pdfReady, pdfFailed } = usePdfStatus(sessionId);

  // 90-second timeout: if the stream is still running and not complete, show a fallback
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    if (isHistoricalReport || complete || streamError) return;
    const t = setTimeout(() => setTimedOut(true), 90_000);
    return () => clearTimeout(t);
  }, [isHistoricalReport, complete, streamError]);

  useEffect(() => {
    if (isHistoricalReport) {
      setLoading(false);
    } else if (complete && Object.keys(sections).length > 0) {
      setReportData(sections);
      setLoading(false);
    } else if (streamError) {
      setLoading(false);
    }
  }, [complete, sections, isHistoricalReport, streamError, setReportData]);


  if (!sessionId) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-muted-foreground p-5 text-center">
        <FileText className="w-12 h-12 mb-4 opacity-20" />
        <p className="text-sm font-semibold text-foreground">No Report Available</p>
        <p className="text-xs mt-2 mb-4 max-w-[250px] opacity-70">
          Upload a survey document or enter coordinates to generate a spatial analysis.
        </p>
        <Button onClick={() => setLocation("/analyse")} variant="outline" className="rounded-xl text-xs h-9 font-semibold">
          Upload Document
        </Button>
      </div>
    );
  }

  if (pipelineError) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-destructive p-5 text-center bg-destructive/5 m-4 rounded-3xl border border-destructive/20">
        <AlertTriangle className="w-12 h-12 mb-4 opacity-80" />
        <p className="text-sm font-bold">Analysis Failed</p>
        <p className="text-xs mt-2 mb-6 max-w-[280px] opacity-80">
          {pipelineError}
        </p>
        <Button onClick={() => setLocation("/analyse")} variant="outline" className="rounded-xl text-xs h-9 font-semibold border-destructive/30 hover:bg-destructive/10 text-destructive">
          Try Again
        </Button>
      </div>
    );
  }

  // SSE stream errored — show dedicated error state
  if (!isHistoricalReport && streamError) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-destructive p-5 text-center bg-destructive/5 m-4 rounded-3xl border border-destructive/20">
        <AlertTriangle className="w-12 h-12 mb-4 opacity-80" />
        <p className="text-sm font-bold">Analysis Failed</p>
        <p className="text-xs mt-2 mb-6 max-w-[280px] opacity-80">
          {streamErrorMessage || "The pipeline encountered an error. Please try again."}
        </p>
        <Button onClick={() => setLocation("/analyse")} variant="outline" className="rounded-xl text-xs h-9 font-semibold border-destructive/30 hover:bg-destructive/10 text-destructive">
          Try Again
        </Button>
      </div>
    );
  }

  if (loading && !isHistoricalReport && stage === "idle") {
    return (
      <div className="flex flex-col h-full items-center justify-center text-muted-foreground p-5 text-center">
        <Loader2 className="w-8 h-8 animate-spin mb-4" />
        <p className="text-sm font-semibold">Initializing Analysis...</p>
      </div>
    );
  }

  const d = isHistoricalReport ? (reportData as any) : sections;
  const hasRiskSummary = !!d.summary;

  const score = d.summary?.overall_risk_score ?? 0;
  const rawVerdict = (d.summary?.traffic_light ?? "UNKNOWN").toUpperCase();
  const verdict = rawVerdict === "GREEN" ? "GREEN — PROCEED"
    : rawVerdict === "AMBER" ? "AMBER — CAUTION"
    : rawVerdict === "RED"   ? "RED — HIGH RISK"
    : "ANALYSIS COMPLETE";
  const verdictColor = rawVerdict === "GREEN" ? "#00A294"
    : rawVerdict === "AMBER" ? "#F59E0B"
    : rawVerdict === "RED"   ? "#EF4444"
    : "#00A294";
  const summary = d.summary?.executive_summary ?? "View the detailed metrics below.";
  const strategicRec = d.summary?.ai_recommendation
    || d.summary?.strategic_recommendation
    || d.summary?.recommendation
    || "Proceed with standard due diligence on local zoning ordinances.";

  const m = {
    elevation: d.terrain_assessment?.elevation_m !== undefined && d.terrain_assessment.elevation_m !== null ? `${d.terrain_assessment.elevation_m}m MSL` : "Not available",
    slope: d.terrain_assessment?.steepness_of_land !== undefined && d.terrain_assessment.steepness_of_land !== null
      ? `${d.terrain_assessment.steepness_of_land}° Avg`
      : d.terrain_assessment?.slope_pct !== undefined && d.terrain_assessment.slope_pct !== null
        ? `${d.terrain_assessment.slope_pct}° Avg`
        : "Not available",
    floodRisk: d.flood_risk_metrics?.level ? `${d.flood_risk_metrics.level}` : "Not available",
    vegDensity: d.terrain_assessment?.ndvi !== undefined && d.terrain_assessment.ndvi !== null
      ? `${Math.round(d.terrain_assessment.ndvi * 100)}% Vegetation Coverage`
      : d.terrain_assessment?.water_presence_index !== undefined && d.terrain_assessment.water_presence_index !== null
        ? `${Math.round(d.terrain_assessment.water_presence_index * 100)}% Water Presence`
        : "Not available",
    roadDist: d.accessibility_development?.distance_to_road_m !== undefined && d.accessibility_development.distance_to_road_m !== null
        ? `${Math.round(d.accessibility_development.distance_to_road_m)}m`
        : "Not available",
    growth: d.growth_potential?.level ? `${d.growth_potential.level}` : "Not available",
  };

  const advisoryFlags = d.advisory_flags || [];
  const titleStatus = d.title_record?.title_status || "Not verified via live registry.";
  
  // Robust state and lga extraction
  const locCtx = d.parcel_geometry?.location_context || {};
  const displayLocation = locCtx.display_location || (locCtx.lga ? `${locCtx.lga}, ${locCtx.state || 'Nigeria'}` : (locCtx.state || "Nigeria"));
  const isApproximateLocation = locCtx.confidence !== undefined && locCtx.confidence !== null && locCtx.confidence < 60;

  // Composite plan data — reads directly from d (mock during test)
  const isComposite = d.parcel_geometry?.is_composite === true;
  const lots: Array<{ lot_id: string; computed_area_sqm?: number; centroid?: [number, number] | null }> =
    isComposite ? (d.parcel_geometry?.lots ?? []) : [];

  const selectedLot = lots.find((l) => l.lot_id === selectedLotId) ?? null;

  // Dynamically swap area readout when a lot is selected
  const displayAreaSqm = selectedLot?.computed_area_sqm ?? d?.parcel_geometry?.computed_area_sqm;
  const areaDisplay = displayAreaSqm !== undefined
    ? displayAreaSqm >= 10000
      ? `${(displayAreaSqm / 10000).toFixed(2)} ha`
      : `${Math.round(displayAreaSqm).toLocaleString()} m²`
    : null;

  const rawProfile = d.premium_elevation_profile?.internal_profile_points || [];
  const activeProfileData = rawProfile.length > 0
    ? rawProfile.map((pt: any) => ({ d: `${Math.round(pt.distance_m)}m`, elevation: pt.elevation_m }))
    : _buildElevationTransect(d.gee_elevation || geeElevation);

  const tl = rawVerdict;
  const t_pal = tl === "GREEN" ? {rgb: "#22C55E", bg: "#F0FDF4", border: "#BBF7D0", sub: "Lower Risk — Proceed"}
    : tl === "AMBER" ? {rgb: "#F59E0B", bg: "#FFFBEB", border: "#FDE68A", sub: "Proceed with Caution"}
    : {rgb: "#EF4444", bg: "#FEF2F2", border: "#FECACA", sub: "High Risk — Review Required"};

  const diff_pct = d.coordinate_validation?.area_discrepancy_pct;
  const stated_area_ha = d.parcel_geometry?.stated_area_ha;
  const computed_area_ha: number | undefined = d.parcel_geometry?.computed_area_ha;
  // Safe area values — guard against undefined producing NaN
  const areaSqm = computed_area_ha != null ? Math.round(computed_area_ha * 10000) : null;
  const centroidLat = d.parcel_geometry?.centroid?.lat;
  const centroidLng = d.parcel_geometry?.centroid?.lng;

  const findings = [];
  if (d.coordinate_validation?.crs_confidence > 70) findings.push({t: "✓ Boundary verified", c: "text-green-600 bg-green-50 border-green-200"});
  else findings.push({t: "⚠ Boundary unverified", c: "text-amber-600 bg-amber-50 border-amber-200"});
  if (d.flood_risk_metrics?.level === "HIGH") findings.push({t: "⚠ High flood risk", c: "text-red-600 bg-red-50 border-red-200"});
  else if (d.flood_risk_metrics?.level === "MEDIUM") findings.push({t: "⚠ Moderate flood risk", c: "text-amber-600 bg-amber-50 border-amber-200"});
  if (d.title_record?.title_status === "Not Checked" || !d.title_record?.title_status) findings.push({t: "⚠ Title unverified", c: "text-amber-600 bg-amber-50 border-amber-200"});
  if (d.growth_potential?.level === "LOW") findings.push({t: "⚠ Low growth area", c: "text-amber-600 bg-amber-50 border-amber-200"});
  if (d.accessibility_development?.utility_row_risk === "WITHIN_ROW") {
    findings.push({t: "⚠ Within Utility RoW", c: "text-rose-600 bg-rose-50 border-rose-200"});
  } else if (d.accessibility_development?.utility_row_risk === "PROXIMATE") {
    findings.push({t: "⚠ Utility Corridor Proximity", c: "text-amber-600 bg-amber-50 border-amber-200"});
  }

  const checklistItems = d.due_diligence_checklist || [
    { priority: "CRITICAL", action: "Engage Surveyor", rationale: "Verify boundary pegs on site." },
    { priority: "HIGH", action: "Conduct Title Search", rationale: "Verify land registry records." },
    { priority: "MEDIUM", action: "Soil Testing", rationale: "Check bearing capacity before foundation design." }
  ];

  return (
    <div className="flex flex-col h-full bg-[var(--report-bg)] font-[var(--report-body)] text-[var(--report-text)]">
      {showPrintModal && sessionId && (
        <PrintAdjustmentModal reportId={sessionId} mode={reportType} exportFormat={exportFormat} onClose={() => setShowPrintModal(false)} onDownloaded={() => toast({ title: `${exportFormat.toUpperCase()} downloaded` })} />
      )}
      
      <div className="flex-1 overflow-y-auto overscroll-none px-5 pt-5 pb-4 space-y-6">
        
        {/* SECTION 1 - DECISION HEADER */}
        <div>
          <div className="flex justify-between items-start mb-4">
             <div>
               <h1 className="text-xl font-bold">Land Intelligence Report</h1>
               <p className="text-xs text-[var(--report-muted)]">{displayLocation}</p>
               {isApproximateLocation && (
                 <p className="text-[10px] font-mono text-[var(--report-muted)] mt-0.5 opacity-80">Location approximate — based on coordinates</p>
               )}
             </div>
             <div className="text-right text-[10px] text-[var(--report-muted)]">
               ID: {sessionId?.substring(0,8)}<br/>Persona: {reportType === "simple" ? "Everyday Buyer" : "Professional"}
             </div>
          </div>

          {!hasRiskSummary ? (
            timedOut
              ? <div className="text-xs text-[var(--report-muted)] py-6 text-center rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)]">Risk assessment unavailable — analysis did not complete.</div>
              : <TrafficLightSkeleton />
          ) : (
            <div className="rounded-[10px] border p-4 flex items-center mt-2" style={{ backgroundColor: t_pal.bg, borderColor: t_pal.border, color: "#0f172a" }}>
              <div className="w-12 h-12 rounded-full mr-4 flex-shrink-0" style={{ backgroundColor: t_pal.rgb }} />
              <div className="flex-1">
                <div className="font-bold text-lg leading-tight" style={{ color: t_pal.rgb }}>{tl}</div>
                <div className="text-sm font-medium">{t_pal.sub}</div>
                <div className="text-xs font-[var(--report-mono)] opacity-70 mt-1">Risk Score: {score.toFixed(1)}/100</div>
                <div className="w-full max-w-[180px] h-3 relative mt-2">
                  <div className="absolute top-1 left-0 right-0 h-0.5 bg-slate-300"></div>
                  <div className="absolute top-0 w-2 h-2 rounded-full" style={{ backgroundColor: t_pal.rgb, left: `${score}%`, transform: 'translateX(-50%)' }}></div>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 mt-4">
            {findings.slice(0,4).map((f, i) => (
              <span key={i} className={`px-3 py-1.5 rounded-md border text-xs font-semibold ${f.c}`}>{f.t}</span>
            ))}
          </div>

          {/* Navigation Button */}
          <div className="mt-4">
            <Button 
              onClick={handleNavigateClick}
              disabled={loadingNav}
              className="w-full h-11 bg-primary hover:bg-primary/90 text-primary-foreground rounded-[10px] shadow-md flex items-center justify-center font-bold text-sm"
            >
              {loadingNav ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Navigation className="w-4 h-4 mr-2" />}
              Navigate to Site
            </Button>
          </div>

        </div>

        {/* SECTION 2 - PARCEL DETAILS */}
        <div>
          <div className="text-[11px] font-bold tracking-widest text-[var(--report-muted)] mb-2 uppercase">Parcel Details</div>
          <table className="w-full text-sm border-collapse">
            <tbody>
              <tr className="border-b border-[var(--report-border)]"><td className="py-2 text-[var(--report-secondary)]">Location</td><td className="py-2">{displayLocation}</td></tr>
              <tr className="border-b border-[var(--report-border)]"><td className="py-2 text-[var(--report-secondary)]">Area</td><td className="py-2">
                {areaSqm != null ? `${areaSqm.toLocaleString()} m²` : areaDisplay ?? "—"}
              </td></tr>
              {(d.parcel_geometry?.perimeter_display || d.parcel_geometry?.perimeter_m) && (
                <tr className="border-b border-[var(--report-border)]"><td className="py-2 text-[var(--report-secondary)]">Perimeter</td><td className="py-2 font-medium">
                  {d.parcel_geometry?.perimeter_display || `${d.parcel_geometry?.perimeter_m?.toFixed(1)}m`}
                </td></tr>
              )}
              <tr className="border-b border-[var(--report-border)]"><td className="py-2 text-[var(--report-secondary)]">Centroid</td><td className="py-2">
                {centroidLat != null && centroidLng != null
                  ? `${centroidLat.toFixed(5)}°N, ${centroidLng.toFixed(5)}°E`
                  : "—"}
              </td></tr>
            </tbody>
          </table>

          {/* AREA & PERIMETER VERIFICATION */}
          {(() => {
            const perimDisp = d.parcel_geometry?.perimeter_display || (d.parcel_geometry?.perimeter_m ? `${d.parcel_geometry.perimeter_m.toFixed(1)}m` : null);
            return (
              <div className="mt-4 rounded-[10px] border border-[var(--report-border)] p-4 bg-[var(--report-surface)]">
                <h3 className="text-xs font-bold text-[var(--report-muted)] uppercase mb-2">Area & Perimeter Verification</h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[var(--report-secondary)]">
                      <th className="pb-2 font-normal">Stated Area</th>
                      <th className="pb-2 font-normal">Computed Area</th>
                      {perimDisp && <th className="pb-2 font-normal">Perimeter</th>}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="font-medium">{stated_area_ha ? `${Math.round(stated_area_ha * 10000).toLocaleString()} m²` : "Not stated"}</td>
                      <td className="font-medium">{areaSqm != null ? `${areaSqm.toLocaleString()} m²` : "—"}</td>
                      {perimDisp && <td className="font-medium">{perimDisp}</td>}
                    </tr>
                  </tbody>
                </table>
                {diff_pct !== null && diff_pct !== undefined && (
                  <div className="mt-2 text-sm">
                    {diff_pct <= 3.0 ? <span className="text-green-600 font-bold">Difference: {diff_pct.toFixed(1)}% — Within tolerance ✓</span> : diff_pct <= 10.0 ? <span className="text-amber-600 font-bold">Difference: {diff_pct.toFixed(1)}% — Minor discrepancy ⚠</span> : <span className="text-red-600 font-bold">Difference: {diff_pct.toFixed(1)}% — Significant discrepancy</span>}
                  </div>
                )}
              </div>
            );
          })()}
        </div>

        {/* SECTION 3 - RISK ASSESSMENT */}
        <div>
          <div className="text-[11px] font-bold tracking-widest text-[var(--report-muted)] mb-2 uppercase">Risk Assessment</div>
          
          {!d.flood_risk_metrics ? (
            timedOut
              ? <div className="text-xs text-[var(--report-muted)] py-4 text-center">Risk data unavailable — satellite providers did not respond in time.</div>
              : <ExecutiveSummarySkeleton />
          ) : (
            <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4 border-l-4" style={{ borderLeftColor: t_pal.rgb }}>
              <h3 className="text-lg font-bold">Flood Risk: {d.flood_risk_metrics?.level}</h3>
              <p className="text-sm text-[var(--report-secondary)] mt-1">{d.flood_risk_metrics?.reason_in_plain_english || "Moderate flood exposure."}</p>
              <div className="mt-3 text-sm flex flex-col gap-1">
                <div>Elevation: <strong>{m.elevation}</strong></div>
                <div>Nearest River: <strong>{d.flood_risk_metrics?.distance_to_nearest_river?.toFixed(0)}m</strong></div>
                <div>Water Presence: <strong>{m.vegDensity}</strong></div>
              </div>
            </div>
          )}

          {!d.terrain_assessment ? (
            timedOut
              ? <div className="text-xs text-[var(--report-muted)] py-4 text-center">Terrain data unavailable — elevation providers did not respond in time.</div>
              : <ExecutiveSummarySkeleton />
          ) : (
            <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4">
              <h3 className="text-md font-bold">Terrain & Access</h3>
              <div className="mt-3 text-sm flex flex-col gap-1">
                <div>Slope: <strong>{m.slope}</strong></div>
                <div>Road Access: <strong>{m.roadDist}</strong></div>
                <div>Suitability: <strong>{d.terrain_assessment?.suitability || "—"}</strong></div>
                {d.accessibility_development?.utility_row_risk && d.accessibility_development.utility_row_risk !== "NONE" && (
                  <div className="mt-1 pt-1 border-t border-[var(--report-border)] flex items-center justify-between">
                    <span>Utility Corridor:</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                      d.accessibility_development.utility_row_risk === "WITHIN_ROW"
                        ? "bg-rose-500/10 text-rose-600 border border-rose-500/20"
                        : "bg-amber-500/10 text-amber-600 border border-amber-500/20"
                    }`}>
                      {d.accessibility_development.utility_row_risk === "WITHIN_ROW" ? "Within Utility RoW" : "Proximate (< 100m)"}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
          
          {!hasRiskSummary ? (
            timedOut
              ? <div className="text-xs text-[var(--report-muted)] py-4 text-center">Growth summary unavailable — analysis did not complete in time.</div>
              : <ExecutiveSummarySkeleton />
          ) : (
            <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4">
              <h3 className="text-md font-bold">Growth Potential: {d.growth_potential?.level}</h3>
              <p className="text-sm mt-2">{summary}</p>
            </div>
          )}
        </div>

        {/* SECTION 4 - WHAT WE OBSERVED */}
        {sessionId && <VIAScanCard reportId={sessionId} hasArrived={!!d.arrived_at} />}

        {/* NEARBY LANDMARKS CONTEXT */}
        <NearbyLandmarksCard landmarksData={d.growth_potential?.nearby_landmarks} />

        {/* NEWS-TO-RISK INTELLIGENCE FEED */}
        <NewsAlertsWidget lga={locCtx?.lga || d?.parcel_lga} state={locCtx?.state || d?.parcel_state} />

        {/* SECTION 5 - DUE DILIGENCE CHECKLIST */}
        <div>
          <h2 className="text-lg font-bold mb-3">WHAT TO DO BEFORE PAYING</h2>
          <div className="space-y-3">
            {checklistItems.map((item: any, i: number) => {
               let bg = "#64748B", label = "GOOD TO KNOW";
               if (item.priority === "CRITICAL") { bg = "#1E3A5F"; label = "MUST DO FIRST"; }
               else if (item.priority === "HIGH") { bg = "#92400E"; label = "IMPORTANT"; }
               else if (item.priority === "MEDIUM") { bg = "#334155"; label = "WORTH DOING"; }
               return (
                 <div key={i} className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4">
                   <span className="text-[10px] font-bold text-white px-2 py-1 rounded-full" style={{ backgroundColor: bg }}>{label}</span>
                   <strong className="block mt-2 text-sm">{item.action}</strong>
                   <p className="text-sm text-[var(--report-secondary)] mt-1">{item.rationale}</p>
                 </div>
               )
            })}
          </div>

          <div className="mt-4 rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4">
            <h3 className="text-sm font-bold mb-2">Estimated Professional Costs</h3>
            <table className="w-full text-sm text-left">
              <thead><tr className="border-b border-[var(--report-border)]"><th className="pb-2">Action</th><th className="pb-2">Cost</th><th className="pb-2">Time</th></tr></thead>
              <tbody>
                <tr className="border-b border-[var(--report-border)]"><td className="py-2">Title Search</td><td className="py-2">₦20k–₦80k</td><td className="py-2">2–5 days</td></tr>
                <tr className="border-b border-[var(--report-border)]"><td className="py-2">Surveyor Verification</td><td className="py-2">₦30k–₦150k</td><td className="py-2">1–3 days</td></tr>
                <tr><td className="py-2">Lawyer Review</td><td className="py-2">₦50k–₦200k</td><td className="py-2">3–7 days</td></tr>
              </tbody>
            </table>
            <p className="text-[10px] text-[var(--report-muted)] mt-2 italic">Estimates are approximate. Always get quotes in advance.</p>
          </div>
        </div>

        {/* SECTION 6 - TECHNICAL APPENDIX */}
        <details className="mt-6" open={reportType === "expert"}>
          <summary className="text-sm font-bold cursor-pointer outline-none bg-slate-100 dark:bg-slate-800 p-3 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
            Technical Details — For Surveyors & GIS Professionals
          </summary>
          <div className="mt-4 space-y-4">
            <div className="rounded-[10px] border border-[var(--report-border)] p-4">
              <h3 className="text-xs font-bold text-[var(--report-muted)] uppercase mb-2">Coordinate Information</h3>
              <table className="w-full text-sm">
                <tbody>
                  <tr className="border-b border-[var(--report-border)]"><td className="py-2 text-[var(--report-secondary)]">Input CRS</td><td className="py-2">{d.coordinate_validation?.detected_crs}</td></tr>
                  <tr className="border-b border-[var(--report-border)]"><td className="py-2 text-[var(--report-secondary)]">Output CRS</td><td className="py-2">WGS84 (EPSG:4326)</td></tr>
                </tbody>
              </table>
            </div>

            {reportType === "expert" && (
              <div className="bg-muted/30 dark:bg-muted/15 border border-border/60 rounded-2xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Terrain Profile</span>
                  {activeProfileData && activeProfileData.length > 0 && (
                    <Badge variant="outline" className="text-[10px] font-mono h-5">
                      X-Section: {activeProfileData[activeProfileData.length - 1]?.d || "3D Grid"}
                    </Badge>
                  )}
                </div>
                {activeProfileData && activeProfileData.length > 0 ? (
                  <div className="h-[90px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={activeProfileData} margin={{ top: 4, right: 0, bottom: 0, left: -24 }}>
                        <defs>
                          <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#0058BD" stopOpacity={0.25} />
                            <stop offset="95%" stopColor="#0058BD" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="d" tick={{ fontSize: 9, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 9, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                        <ReTooltip contentStyle={{ borderRadius: 10, fontSize: 11, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))", color: "hsl(var(--foreground))" }} formatter={(v) => [`${v}m`, "Elevation"]} />
                        <Area type="monotone" dataKey="elevation" stroke="#0058BD" strokeWidth={2} fill="url(#elevGrad)" dot={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="text-xs text-muted-foreground py-4 text-center">
                    Terrain profile unavailable — elevation providers did not respond in time.
                  </div>
                )}
              </div>
            )}

            {reportType === "expert" && sessionId && parcelCoords && (
              <TopographicAssessmentSection reportId={sessionId} parcelCoords={parcelCoords} />
            )}
          </div>
        </details>

        {/* SECTION 7 - LEGAL DISCLAIMER */}
        <div className="mt-8 pt-4 border-t border-[var(--report-border)] text-center text-[11px] text-[var(--report-muted)] italic">
          This report is an advisory screening based on publicly available geospatial data and satellite imagery. It is not a legal survey, a title opinion, or a professional engineering assessment.<br/><br/>
          Always engage a SURCON-registered surveyor and a qualified property lawyer before committing funds to any land transaction.
        </div>
      </div>

      {/* Sticky footer */}
      <div className="flex-shrink-0 px-5 pt-4 pb-[calc(env(safe-area-inset-bottom,0px)+16px)] lg:pb-5 border-t border-[var(--report-border)] space-y-3 bg-[var(--report-bg)]">
        <div className="flex p-1 bg-slate-100 dark:bg-slate-800 rounded-full gap-1 border border-[var(--report-border)]">
          {(["simple", "expert"] as const).map((t) => (
            <button key={t} onClick={() => setReportType(t)} className={cn("flex-1 py-2.5 px-3 rounded-full text-xs font-semibold transition-all duration-200", reportType === t ? "bg-white dark:bg-slate-700 shadow-sm text-black dark:text-white" : "text-slate-500 dark:text-slate-400 hover:text-black dark:hover:text-white")}>
              {t === "simple" ? "Everyday Buyer" : "Professional"}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-center text-[var(--report-muted)]">
          {reportType === "simple" ? "Standard summary suitable for everyday buyers." : "Full technical report with GIS data."}
        </p>
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1 rounded-full h-12 text-sm font-semibold border-[var(--report-border)] hover:bg-slate-50 dark:hover:bg-slate-800" disabled={!sessionId} onClick={() => { if (!sessionId) return; setExportFormat("png"); setShowPrintModal(true); }}>
            <Share2 className="w-3.5 h-3.5 mr-1.5" /> Save PNG Card
          </Button>
          <Button 
            className="flex-1 rounded-full h-12 bg-primary hover:bg-primary/90 text-primary-foreground shadow-md text-sm font-semibold" 
            disabled={!sessionId || (!pdfReady && !pdfFailed && complete && !isHistoricalReport)} 
            onClick={() => { setExportFormat("pdf"); setShowPrintModal(true); }}
          >
            {(!pdfReady && !pdfFailed && complete && !isHistoricalReport) ? (
              <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Preparing PDF...</>
            ) : pdfFailed ? (
              <><AlertTriangle className="w-3.5 h-3.5 mr-1.5" /> PDF Error</>
            ) : (
              <><Download className="w-3.5 h-3.5 mr-1.5" /> Export PDF</>
            )}
          </Button>
        </div>
      </div>

      {showNav && navData && (
        <SiteNavigationPanel 
          navData={navData} 
          reportData={d}
          onClose={() => setShowNav(false)} 
          onArrivalComplete={() => {
            // Optimistically update the UI to show the new arrived message
            setReportData({ ...d, arrived_at: new Date().toISOString() });
          }} 
        />
      )}
    </div>
  );
}
