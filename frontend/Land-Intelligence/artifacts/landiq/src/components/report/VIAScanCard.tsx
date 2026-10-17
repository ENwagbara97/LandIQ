/**
 * LandIQ — VIAScanCard.tsx
 * Visual Intelligence Advisor — Report Card Component
 *
 * Sits between the "Terrain & Access" section and "Growth Potential" section.
 * Polls /api/via/status/{reportId} every 3s after triggering.
 * Renders loading → content → fallback states per VIA Master Prompt Section 4.
 *
 * Design Spec:
 *   - Left border: 3px solid var(--color-primary)
 *   - Header: Eye icon + "VISUAL SITE SCAN" + "ADVISORY ONLY" badge
 *   - Content: Inter 14px, text-foreground, line-height 1.7
 *   - Key observations strip: 2-3 icon+label items (hidden when confidence=low)
 *   - Disclaimer footer: italic, text-muted-foreground
 */

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Eye,
  Route,
  Waves,
  AlertTriangle,
  Home,
  Store,
  Factory,
  MapPin,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface VIARiskObservations {
  erosion_visible: boolean;
  marshy_terrain_visible: boolean;
  industrial_activity_visible: boolean;
  flooding_evidence_visible: boolean;
  encroachment_risk_visual: boolean;
}

interface VIACallA {
  image_quality: {
    satellite_clarity: "clear" | "moderate" | "poor";
  };
  immediate_surroundings_250m: {
    road_access: { road_visible: boolean; road_type: string };
    water_features: { water_body_visible: boolean };
    settlement_pattern: {
      settlement_type: string;
      commercial_activity_visible: boolean;
    };
    risk_observations: VIARiskObservations;
  };
  confidence: {
    overall_confidence: "high" | "medium" | "low";
  };
}

interface VIAResult {
  status: "pending" | "complete" | "timeout" | "error";
  call_a?: VIACallA;
  call_b_text?: string;
  advisory_flags?: string[];
}

interface VIAStatusResponse {
  status: "pending" | "complete" | "timeout" | "error";
  report_id: string;
  via_result: VIAResult | null;
  completed_at?: string;
}

interface VIAScanCardProps {
  reportId: string;
  apiBase?: string;
  hasArrived?: boolean;
}

// ── Key observation detection ─────────────────────────────────────────────────

interface ObservationChip {
  icon: React.ReactNode;
  label: string;
  level: "neutral" | "warning" | "danger";
}

function buildObservations(callA: VIACallA): ObservationChip[] {
  const chips: ObservationChip[] = [];
  const surr = callA.immediate_surroundings_250m;
  const risk = surr.risk_observations;

  if (surr.road_access.road_visible) {
    chips.push({ icon: <Route size={14} />, label: "Road nearby", level: "neutral" });
  }
  if (surr.water_features.water_body_visible) {
    chips.push({ icon: <Waves size={14} />, label: "Water visible", level: "warning" });
  }
  if (risk.erosion_visible) {
    chips.push({ icon: <AlertTriangle size={14} />, label: "Erosion risk", level: "danger" });
  }
  if (surr.settlement_pattern.settlement_type.toLowerCase().includes("informal")) {
    chips.push({ icon: <Home size={14} />, label: "Informal settlement", level: "warning" });
  }
  if (surr.settlement_pattern.commercial_activity_visible) {
    chips.push({ icon: <Store size={14} />, label: "Commercial activity", level: "neutral" });
  }
  if (risk.industrial_activity_visible) {
    chips.push({ icon: <Factory size={14} />, label: "Industrial nearby", level: "danger" });
  }

  return chips.slice(0, 3); // max 3 chips
}

const levelClasses: Record<string, string> = {
  neutral: "text-primary",
  warning: "text-amber-500",
  danger:  "text-destructive",
};

// ── Dot pulse loading animation ───────────────────────────────────────────────

function DotPulse() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="Loading">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce"
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.8s" }}
        />
      ))}
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export function VIAScanCard(props: VIAScanCardProps) {
  const { reportId, apiBase = "http://127.0.0.1:8000" } = props;
  const [viaStatus, setViaStatus] = useState<"pending" | "complete" | "timeout" | "error" | "low_quality">("pending");
  const [viaResult, setViaResult] = useState<VIAResult | null>(null);
  const [triggered, setTriggered] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Trigger VIA on mount
  const triggerVia = useCallback(async () => {
    if (triggered) return;
    setTriggered(true);
    try {
      await fetch(`${apiBase}/api/via/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_id: reportId }),
      });
    } catch {
      // trigger failure — polling will surface the error state
    }
  }, [reportId, apiBase, triggered]);

  // Poll every 3 seconds
  const pollStatus = useCallback(async () => {
    try {
      const resp = await fetch(`${apiBase}/api/via/status/${reportId}`);
      if (!resp.ok) return;
      const data: VIAStatusResponse = await resp.json();
      setViaStatus(data.status);
      if (data.via_result) {
        setViaResult(data.via_result);
      }
      if (data.status === "complete" || data.status === "timeout" || data.status === "error") {
        if (pollRef.current) clearInterval(pollRef.current);
      }
    } catch {
      // network glitch — keep polling
    }
  }, [reportId, apiBase]);

  useEffect(() => {
    triggerVia();
    pollRef.current = setInterval(pollStatus, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [triggerVia, pollStatus]);

  // ── Render helpers ──────────────────────────────────────────────────────────

  const isLoading = viaStatus === "pending";
  const isComplete = viaStatus === "complete" && viaResult;
  const isFailed   = viaStatus === "timeout" || viaStatus === "error";

  const confidence = viaResult?.call_a?.confidence?.overall_confidence ?? "low";
  const showObservations = isComplete && confidence !== "low";
  const poorClarity = viaResult?.call_a?.image_quality?.satellite_clarity === "poor";
  const chips = isComplete && viaResult?.call_a ? buildObservations(viaResult.call_a) : [];

  // Split call_b_text into paragraphs
  const paragraphs = viaResult?.call_b_text
    ? viaResult.call_b_text.split(/\n\n+/).filter(Boolean)
    : [];

  // ── Card ─────────────────────────────────────────────────────────────────────

  return (
    <div
      id="via-scan-card"
      className="rounded-md bg-card"
      style={{
        borderLeft: "3px solid var(--color-primary, hsl(var(--primary)))",
        padding: "24px",
      }}
    >
      {/* Card Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Eye size={16} className="text-primary" />
          <span
            className="text-muted-foreground font-semibold tracking-widest"
            style={{ fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.1em" }}
          >
            Visual Site Scan
          </span>
        </div>
        <span
          className="text-muted-foreground rounded-full border border-border px-2 py-0.5"
          style={{ fontSize: "11px" }}
        >
          Advisory Only
        </span>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-muted-foreground" style={{ fontSize: "14px" }}>
            <DotPulse />
            <span>Scanning satellite imagery for your area…</span>
          </div>
          {/* animated progress strip */}
          <div className="h-0.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary rounded-full animate-pulse"
              style={{ width: "60%" }}
            />
          </div>
        </div>
      )}

      {/* Low Quality Imagery fallback */}
      {((viaStatus as string) === "low_quality" || (viaResult?.status as string) === "low_quality") && (
        <div className="rounded-xl border-l-4 border-amber-500 bg-amber-500/10 p-4 space-y-2">
          <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-bold text-sm">
            <AlertTriangle size={18} className="flex-shrink-0" />
            <span>Satellite Image Quality Limited</span>
          </div>
          <p className="text-xs text-foreground/80 leading-relaxed">
            {(viaResult as any)?.error_detail || "Satellite imagery quality is limited for this area. The satellite image is unclear or outdated. Visual observations cannot be reliably made from this image. A physical site visit is strongly recommended."}
          </p>
          <p className="text-[11px] text-muted-foreground font-semibold pt-1">
            Try switching to a different map layer (e.g., Esri Hybrid) using the layer toggle on the map.
          </p>
        </div>
      )}

      {/* Timeout / Error fallback */}
      {isFailed && (viaStatus as string) !== "low_quality" && (viaResult?.status as string) !== "low_quality" && (
        <p
          className="text-muted-foreground italic"
          style={{ fontSize: "14px", lineHeight: 1.7 }}
        >
          Visual scan unavailable for this report. Physical site inspection is recommended.
        </p>
      )}

      {/* Complete State */}
      {isComplete && (
        <>
          {/* Poor clarity caveat */}
          {poorClarity && (
            <p
              className="text-amber-500 mb-3"
              style={{ fontSize: "13px", lineHeight: 1.6 }}
            >
              Satellite imagery for this area has limited clarity. The visual observations
              below are lower confidence than usual. We recommend placing extra emphasis on
              a physical site visit.
            </p>
          )}

          {/* Main text paragraphs */}
          <div className="space-y-3">
            {paragraphs.map((para, i) => (
              <p
                key={i}
                className="text-foreground"
                style={{ fontSize: "14px", lineHeight: 1.7, fontFamily: "Inter, sans-serif" }}
              >
                {para.trim()}
              </p>
            ))}
          </div>

          {/* Key Observations Strip */}
          {showObservations && chips.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-4">
              {chips.map((chip, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-1.5 ${levelClasses[chip.level]}`}
                  style={{ fontSize: "12px", fontWeight: 500 }}
                >
                  {chip.icon}
                  <span>{chip.label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Advisory flags (VIA_ flags rendered with Eye icon) */}
          {viaResult?.advisory_flags && viaResult.advisory_flags.length > 0 && (
            <div className="mt-4 space-y-2">
              {viaResult.advisory_flags.map((flag, i) => {
                const text = flag.replace(/^VIA_\w+:\s*/, "");
                return (
                  <div key={i} className="flex gap-2 items-start">
                    <Eye size={13} className="text-muted-foreground mt-0.5 shrink-0" />
                    <p className="text-muted-foreground" style={{ fontSize: "12px", lineHeight: 1.6 }}>
                      <span className="uppercase tracking-wide" style={{ fontSize: "10px" }}>
                        Satellite Observation —{" "}
                      </span>
                      {text}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {/* Divider + Disclaimer */}
          <div className="mt-5 pt-4 border-t border-border">
            <p
              className="text-muted-foreground italic"
              style={{ fontSize: "10px", lineHeight: 1.6 }}
            >
              {props.hasArrived ? (
                <>You are now at the site — your physical eyes are the ground truth. Satellite observations above may be 1–3 years old.</>
              ) : (
                <>Visual observations based on satellite imagery (may be 1–3 years old). Verify on-site.</>
              )}
            </p>
          </div>
        </>
      )}
    </div>
  );
}

export default VIAScanCard;
