import { useState, useRef, useEffect } from "react";
import { useLocation } from "wouter";
import { useAppContext } from "@/context/AppContext";
import { MapView } from "@/components/map/MapView";
import { AnalysePanel } from "@/components/analyse/AnalysePanel";
import { GatePanel } from "@/components/gate/GatePanel";
import { ReportPanel } from "@/components/report/ReportPanel";
import { HistoryPanel } from "@/components/history/HistoryPanel";
import { useMobile } from "@/hooks/use-mobile";
import { ChevronLeft, ChevronRight, ScanLine, FileText } from "lucide-react";

export function Dashboard() {
  const [location, setLocation] = useLocation();
  const { analysisState } = useAppContext();
  const isMobile = useMobile();

  // Desktop sidebar collapse
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  const showRight =
    analysisState === "gate" ||
    analysisState === "complete" ||
    location === "/gate" ||
    location === "/report";

  /* ─── MOBILE ─── */
  if (isMobile) {
    const isPanelOpen =
      location === "/analyse" ||
      location === "/gate" ||
      location === "/report" ||
      location === "/history";

    const isGate = location === "/gate";

    return (
      <MobileLayout
        isPanelOpen={isPanelOpen}
        isGate={isGate}
        location={location}
        onClose={() => setLocation("/")}
      />
    );
  }

  /* ─── DESKTOP ─── */
  return (
    <div className="flex w-full h-full relative overflow-hidden bg-background">

      {/* LEFT SIDEBAR */}
      {leftOpen ? (
        <div className="relative flex-shrink-0 h-full border-r border-border bg-card/60 backdrop-blur-sm overflow-hidden z-10"
          style={{ width: 360 }}>
          <div className="h-full overflow-y-auto">
            <AnalysePanel />
          </div>
          {/* Collapse tab — bottom edge, full width strip */}
          <button
            onClick={() => setLeftOpen(false)}
            title="Collapse panel"
            className="absolute bottom-0 left-0 right-0 h-10 border-t border-border bg-muted/60 hover:bg-muted flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground transition-colors z-20"
          >
            <ChevronLeft className="w-4 h-4" />
            <span className="text-xs font-medium">Collapse</span>
          </button>
        </div>
      ) : (
        /* Collapsed left strip — click anywhere to expand */
        <div
          onClick={() => setLeftOpen(true)}
          className="relative w-12 flex-shrink-0 h-full border-r border-border bg-card/60 z-10 flex flex-col items-center py-6 cursor-pointer hover:bg-muted/40 transition-colors group"
          title="Expand Upload panel"
        >
          <div className="w-8 h-8 rounded-full bg-primary/10 group-hover:bg-primary/20 flex items-center justify-center mb-auto transition-colors">
            <ChevronRight className="w-4 h-4 text-primary" />
          </div>
          <div className="flex flex-col items-center gap-2 mb-auto">
            <ScanLine className="w-4 h-4 text-muted-foreground/40" />
            <p
              className="text-[10px] font-bold text-muted-foreground/50 uppercase tracking-widest"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            >
              Upload
            </p>
          </div>
        </div>
      )}

      {/* CENTER — Map */}
      <div className="flex-1 relative z-0 min-w-0">
        <MapView />
      </div>

      {/* RIGHT SIDEBAR */}
      {showRight && (
        rightOpen ? (
          <div
            className="relative flex-shrink-0 h-full border-l border-border bg-card/60 backdrop-blur-sm overflow-hidden z-10"
            style={{ width: 400 }}
          >
            {/* Collapse tab — bottom edge */}
            <button
              onClick={() => setRightOpen(false)}
              title="Collapse panel"
              className="absolute bottom-0 left-0 right-0 h-10 border-t border-border bg-muted/60 hover:bg-muted flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground transition-colors z-20"
            >
              <span className="text-xs font-medium">Collapse</span>
              <ChevronRight className="w-4 h-4" />
            </button>
            <div className="h-full overflow-y-auto pb-10">
              {analysisState === "complete" || location === "/report"
                ? <ReportPanel />
                : <GatePanel />}
            </div>
          </div>
        ) : (
          /* Collapsed right strip — click anywhere to expand */
          <div
            onClick={() => setRightOpen(true)}
            className="relative w-12 flex-shrink-0 h-full border-l border-border bg-card/60 z-10 flex flex-col items-center py-6 cursor-pointer hover:bg-muted/40 transition-colors group"
            title="Expand Report panel"
          >
            <div className="w-8 h-8 rounded-full bg-primary/10 group-hover:bg-primary/20 flex items-center justify-center mb-auto transition-colors">
              <ChevronLeft className="w-4 h-4 text-primary" />
            </div>
            <div className="flex flex-col items-center gap-2 mb-auto">
              <FileText className="w-4 h-4 text-muted-foreground/40" />
              <p
                className="text-[10px] font-bold text-muted-foreground/50 uppercase tracking-widest"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
              >
                Report
              </p>
            </div>
          </div>
        )
      )}

      {/* History full-screen overlay */}
      {location === "/history" && (
        <div className="absolute inset-0 z-20 bg-background/96 backdrop-blur-md overflow-y-auto">
          <div className="max-w-3xl mx-auto py-10 px-6 h-full">
            <HistoryPanel />
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Swipeable Mobile Sheet ─────────────────────────────────────── */

function MobileLayout({
  isPanelOpen,
  isGate,
  location,
  onClose,
}: {
  isPanelOpen: boolean;
  isGate: boolean;
  location: string;
  onClose: () => void;
}) {
  const NAV_HEIGHT = 72;
  const HEADER_CLEARANCE = 64;

  // For gate screen always full, for others start at half
  const defaultSnap = isGate ? "full" : "half";
  const [snap, setSnap] = useState<"half" | "full">(defaultSnap);

  // Reset snap point when panel or location changes
  useEffect(() => {
    setSnap(isGate ? "full" : "half");
  }, [location, isGate]);

  const sheetRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startY: number; startTop: number } | null>(null);

  const getTopPx = (s: "half" | "full") => {
    const h = window.innerHeight;
    return s === "full"
      ? HEADER_CLEARANCE
      : Math.round(h * 0.48);
  };

  const onTouchStart = (e: React.TouchEvent) => {
    const sheet = sheetRef.current;
    if (!sheet) return;
    const rect = sheet.getBoundingClientRect();
    dragRef.current = { startY: e.touches[0].clientY, startTop: rect.top };
    sheet.style.transition = "none";
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (!dragRef.current || !sheetRef.current) return;
    const deltaY = e.touches[0].clientY - dragRef.current.startY;
    const newTop = Math.max(HEADER_CLEARANCE, Math.min(window.innerHeight * 0.82, dragRef.current.startTop + deltaY));
    sheetRef.current.style.top = `${newTop}px`;
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    if (!dragRef.current || !sheetRef.current) return;
    const deltaY = e.changedTouches[0].clientY - dragRef.current.startY;
    sheetRef.current.style.transition = "";
    sheetRef.current.style.top = "";
    dragRef.current = null;

    if (deltaY > 90) {
      if (snap === "full") {
        setSnap("half");
      } else {
        onClose();
      }
    } else if (deltaY < -70) {
      setSnap("full");
    }
  };

  // Determine the top in CSS (used when not dragging)
  const topStyle = snap === "full" ? `${HEADER_CLEARANCE}px` : "48%";

  return (
    <div className="relative w-full h-full overflow-hidden">
      {/* Full-screen map always behind */}
      <div className="absolute inset-0">
        <MapView />
      </div>

      {/* Scrim */}
      {isPanelOpen && (
        <div
          className="absolute inset-x-0 top-0 bg-black/25 z-[70] pointer-events-none"
          style={{ bottom: NAV_HEIGHT }}
        />
      )}

      {/* Bottom sheet */}
      {isPanelOpen && (
        <div
          ref={sheetRef}
          className="absolute inset-x-0 z-[80] flex flex-col overflow-hidden shadow-2xl"
          style={{
            top: topStyle,
            bottom: NAV_HEIGHT,
            borderRadius: isGate ? "20px 20px 0 0" : "28px 28px 0 0",
            background: isGate ? "#0D1523" : "hsl(var(--background))",
            borderTop: isGate ? "1px solid #1E2D3D" : "1px solid hsl(var(--border) / 0.4)",
            transition: "top 0.3s cubic-bezier(0.32, 0.72, 0, 1)",
          }}
        >
          {/* Drag handle */}
          <div
            className="flex-shrink-0 pt-3 pb-1 flex justify-center cursor-grab active:cursor-grabbing touch-none"
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
          >
            <div className="w-10 h-1 rounded-full"
              style={{ background: isGate ? "rgba(255,255,255,0.12)" : "hsl(var(--muted-foreground)/20%)" }}
            />
          </div>

          {/* Sheet content */}
          <div className="flex-1 overflow-y-auto overscroll-contain">
            {location === "/analyse" && <AnalysePanel />}
            {location === "/gate" && <GatePanel />}
            {location === "/report" && <ReportPanel />}
            {location === "/history" && <HistoryPanel />}
          </div>
        </div>
      )}
    </div>
  );
}
