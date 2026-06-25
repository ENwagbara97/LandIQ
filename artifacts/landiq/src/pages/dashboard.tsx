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

  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  const showRight =
    analysisState === "gate" ||
    analysisState === "complete" ||
    location === "/gate" ||
    location === "/report";

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

  return (
    <div className="flex w-full h-full relative overflow-hidden bg-background">

      {/* LEFT SIDEBAR */}
      {leftOpen ? (
        <div
          className="relative flex-shrink-0 h-full border-r border-border bg-card/60 backdrop-blur-sm z-10"
          style={{ width: 360 }}
        >
          <div className="h-full overflow-y-auto">
            <AnalysePanel />
          </div>
        </div>
      ) : (
        <div
          onClick={() => setLeftOpen(true)}
          className="relative w-11 flex-shrink-0 h-full border-r border-border bg-card/60 z-10 flex flex-col items-center justify-center gap-3 cursor-pointer hover:bg-muted/40 transition-colors group"
          title="Expand panel"
        >
          <ChevronRight className="w-4 h-4 text-muted-foreground/60 group-hover:text-primary transition-colors" />
          <ScanLine className="w-4 h-4 text-muted-foreground/30" />
          <p
            className="text-[10px] font-bold text-muted-foreground/40 uppercase tracking-widest"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            Upload
          </p>
        </div>
      )}

      {/* CENTER MAP — edge-tab collapse buttons live here so they can overlap sidebar edges */}
      <div className="flex-1 relative z-0 min-w-0">
        <MapView />

        {/* Left edge-tab: collapse left sidebar */}
        {leftOpen && (
          <button
            onClick={() => setLeftOpen(false)}
            title="Collapse"
            className="absolute left-0 top-[44%] -translate-y-1/2 w-5 h-12 bg-card/90 border border-border border-l-0 rounded-r-xl flex items-center justify-center hover:bg-muted shadow-sm z-10 transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        )}

        {/* Right edge-tab: collapse right sidebar */}
        {showRight && rightOpen && (
          <button
            onClick={() => setRightOpen(false)}
            title="Collapse"
            className="absolute right-0 top-[44%] -translate-y-1/2 w-5 h-12 bg-card/90 border border-border border-r-0 rounded-l-xl flex items-center justify-center hover:bg-muted shadow-sm z-10 transition-colors"
          >
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        )}
      </div>

      {/* RIGHT SIDEBAR */}
      {showRight && (
        rightOpen ? (
          <div
            className="relative flex-shrink-0 h-full border-l border-border bg-card/60 backdrop-blur-sm overflow-hidden z-10"
            style={{ width: 400 }}
          >
            <div className="h-full overflow-y-auto">
              {analysisState === "complete" || location === "/report"
                ? <ReportPanel />
                : <GatePanel />}
            </div>
          </div>
        ) : (
          <div
            onClick={() => setRightOpen(true)}
            className="relative w-11 flex-shrink-0 h-full border-l border-border bg-card/60 z-10 flex flex-col items-center justify-center gap-3 cursor-pointer hover:bg-muted/40 transition-colors group"
            title="Expand panel"
          >
            <ChevronLeft className="w-4 h-4 text-muted-foreground/60 group-hover:text-primary transition-colors" />
            <FileText className="w-4 h-4 text-muted-foreground/30" />
            <p
              className="text-[10px] font-bold text-muted-foreground/40 uppercase tracking-widest"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            >
              Report
            </p>
          </div>
        )
      )}

      {/* History overlay */}
      {location === "/history" && (
        <div className="absolute inset-0 z-20 bg-background/95 backdrop-blur-md overflow-y-auto">
          <div className="max-w-3xl mx-auto py-10 px-6">
            <HistoryPanel />
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Mobile swipeable bottom sheet ─────────────────────────────── */

const HEADER_CLEARANCE = 64;
const NAV_HEIGHT = 72;

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
  const [snap, setSnap] = useState<"half" | "full">(isGate ? "full" : "half");

  // Reset snap when location changes
  useEffect(() => {
    setSnap(isGate ? "full" : "half");
  }, [location, isGate]);

  // Refs needed for drag logic (avoids stale closure)
  const sheetRef = useRef<HTMLDivElement>(null);
  const dragHandleRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startY: number; startTop: number } | null>(null);
  const snapRef = useRef(snap);
  snapRef.current = snap;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Attach touch listeners once via useEffect — document-level so
  // the drag continues even when finger moves off the handle element
  useEffect(() => {
    const handle = dragHandleRef.current;
    const sheet = sheetRef.current;
    if (!handle || !sheet) return;

    const onMove = (e: TouchEvent) => {
      if (!dragRef.current) return;
      e.preventDefault();
      const deltaY = e.touches[0].clientY - dragRef.current.startY;
      const raw = dragRef.current.startTop + deltaY;
      const clamped = Math.max(HEADER_CLEARANCE, Math.min(window.innerHeight * 0.82, raw));
      sheet.style.top = `${clamped}px`;
    };

    const onEnd = (e: TouchEvent) => {
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      if (!dragRef.current) return;
      const deltaY = e.changedTouches[0].clientY - dragRef.current.startY;
      sheet.style.transition = "";
      sheet.style.top = "";
      dragRef.current = null;

      if (deltaY > 90) {
        if (snapRef.current === "full") setSnap("half");
        else onCloseRef.current();
      } else if (deltaY < -70) {
        setSnap("full");
      }
    };

    const onStart = (e: TouchEvent) => {
      e.preventDefault();
      const rect = sheet.getBoundingClientRect();
      dragRef.current = { startY: e.touches[0].clientY, startTop: rect.top };
      sheet.style.transition = "none";
      document.addEventListener("touchmove", onMove, { passive: false });
      document.addEventListener("touchend", onEnd);
    };

    handle.addEventListener("touchstart", onStart, { passive: false });
    return () => {
      handle.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
    };
  }, [isPanelOpen]);

  const topStyle = snap === "full" ? `${HEADER_CLEARANCE}px` : "48%";

  return (
    <div className="relative w-full h-full overflow-hidden">
      <div className="absolute inset-0">
        <MapView />
      </div>

      {isPanelOpen && (
        <div
          className="absolute inset-x-0 top-0 bg-black/20 pointer-events-none z-[70]"
          style={{ bottom: NAV_HEIGHT }}
        />
      )}

      {isPanelOpen && (
        <div
          ref={sheetRef}
          className="absolute inset-x-0 z-[80] flex flex-col overflow-hidden shadow-2xl"
          style={{
            top: topStyle,
            bottom: NAV_HEIGHT,
            borderRadius: "24px 24px 0 0",
            background: isGate ? "#0D1523" : "hsl(var(--background))",
            borderTop: isGate ? "1px solid #1E2D3D" : "1px solid hsl(var(--border) / 0.4)",
            transition: "top 0.32s cubic-bezier(0.32, 0.72, 0, 1)",
          }}
        >
          {/* Drag handle — touch listeners attached via useEffect above */}
          <div
            ref={dragHandleRef}
            className="flex-shrink-0 py-3 flex flex-col items-center gap-1 cursor-grab select-none"
            style={{ touchAction: "none" }}
          >
            <div
              className="w-10 h-1 rounded-full"
              style={{
                background: isGate
                  ? "rgba(255,255,255,0.15)"
                  : "hsl(var(--muted-foreground) / 0.25)",
              }}
            />
            {/* Snap indicator dots */}
            <div className="flex gap-1 mt-0.5">
              <span className={`w-1 h-1 rounded-full transition-colors ${snap === "half" ? (isGate ? "bg-white/40" : "bg-foreground/30") : (isGate ? "bg-white/15" : "bg-foreground/10")}`} />
              <span className={`w-1 h-1 rounded-full transition-colors ${snap === "full" ? (isGate ? "bg-white/40" : "bg-foreground/30") : (isGate ? "bg-white/15" : "bg-foreground/10")}`} />
            </div>
          </div>

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
