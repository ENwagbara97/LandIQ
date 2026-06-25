import { useState } from "react";
import { useLocation } from "wouter";
import { useAppContext } from "@/context/AppContext";
import { MapView } from "@/components/map/MapView";
import { AnalysePanel } from "@/components/analyse/AnalysePanel";
import { GatePanel } from "@/components/gate/GatePanel";
import { ReportPanel } from "@/components/report/ReportPanel";
import { HistoryPanel } from "@/components/history/HistoryPanel";
import { useMobile } from "@/hooks/use-mobile";
import { ChevronLeft, ChevronRight, ScanLine, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

export function Dashboard() {
  const [location] = useLocation();
  const { analysisState } = useAppContext();
  const isMobile = useMobile();

  // Desktop sidebar collapse state
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  const showRight = analysisState === 'gate' || analysisState === 'complete' ||
    location === '/gate' || location === '/report';

  /* ─── MOBILE ─── */
  if (isMobile) {
    const isPanelOpen = location === '/analyse' || location === '/gate' ||
      location === '/report' || location === '/history';

    const panelContent = () => {
      if (location === '/analyse') return <AnalysePanel />;
      if (location === '/gate') return <GatePanel />;
      if (location === '/report') return <ReportPanel />;
      if (location === '/history') return <HistoryPanel />;
      return null;
    };

    const panelTitle = () => {
      if (location === '/analyse') return 'New Analysis';
      if (location === '/gate') return 'Gate & Verify';
      if (location === '/report') return 'Report';
      if (location === '/history') return 'Recent Parcels';
      return '';
    };

    return (
      <div className="relative w-full h-full overflow-hidden">
        {/* Full-screen map always behind */}
        <div className="absolute inset-0 top-0">
          <MapView />
        </div>

        {/* Bottom sheet — sits above map, below nav (z-[80]) */}
        {isPanelOpen && (
          <>
            {/* Scrim — only covers map, stops above nav (bottom-[72px]) */}
            <div
              className="absolute inset-x-0 top-0 bg-black/30 z-[70]"
              style={{ bottom: 72 }}
            />

            {/* Sheet panel */}
            <div
              className="absolute inset-x-0 bg-background rounded-t-[28px] overflow-hidden z-[80] flex flex-col shadow-2xl border-t border-border/40"
              style={{ bottom: 72, top: '35%' }}
            >
              {/* Drag handle */}
              <div className="flex-shrink-0 pt-3 pb-1 flex justify-center">
                <div className="w-10 h-1 rounded-full bg-muted-foreground/20" />
              </div>

              {/* Sheet content — scrollable */}
              <div className="flex-1 overflow-y-auto overscroll-contain">
                {location === '/history' ? (
                  <HistoryPanel />
                ) : (
                  <div className="pb-6">
                    {location === '/analyse' && <AnalysePanel />}
                    {location === '/gate' && <GatePanel />}
                    {location === '/report' && <ReportPanel />}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    );
  }

  /* ─── DESKTOP ─── */
  return (
    <div className="flex w-full h-full relative overflow-hidden bg-background">

      {/* LEFT SIDEBAR — Analyse / Upload */}
      {leftOpen ? (
        <div className="relative w-[360px] flex-shrink-0 h-full border-r border-border bg-card/60 backdrop-blur-md overflow-hidden z-10 shadow-[2px_0_16px_rgba(0,0,0,0.03)]">
          <div className="h-full overflow-y-auto">
            <AnalysePanel />
          </div>
          {/* Collapse toggle */}
          <button
            onClick={() => setLeftOpen(false)}
            className="absolute top-1/2 -translate-y-1/2 -right-3 w-6 h-12 bg-white dark:bg-[#1A1D24] border border-border rounded-full flex items-center justify-center shadow-md hover:bg-muted z-20 transition-colors"
            title="Collapse panel"
          >
            <ChevronLeft className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        </div>
      ) : (
        /* Collapsed left strip */
        <div className="relative w-11 flex-shrink-0 h-full border-r border-border bg-card/60 z-10 flex flex-col items-center justify-between py-6 shadow-[2px_0_16px_rgba(0,0,0,0.03)]">
          <button
            onClick={() => setLeftOpen(true)}
            className="w-8 h-8 rounded-full bg-primary/10 hover:bg-primary/20 flex items-center justify-center transition-colors"
            title="Expand panel"
          >
            <ChevronRight className="w-3.5 h-3.5 text-primary" />
          </button>
          <div className="flex flex-col items-center gap-2">
            <ScanLine className="w-4 h-4 text-muted-foreground/50" />
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-widest leading-none" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>
              Upload
            </p>
          </div>
          <div className="w-4 h-4" />
        </div>
      )}

      {/* CENTER — Map */}
      <div className="flex-1 relative z-0">
        <MapView />
      </div>

      {/* RIGHT SIDEBAR — Gate / Report */}
      {showRight && (
        rightOpen ? (
          <div className="relative w-[400px] flex-shrink-0 h-full border-l border-border bg-card/60 backdrop-blur-md overflow-hidden z-10 shadow-[-2px_0_16px_rgba(0,0,0,0.03)]">
            {/* Collapse toggle */}
            <button
              onClick={() => setRightOpen(false)}
              className="absolute top-1/2 -translate-y-1/2 -left-3 w-6 h-12 bg-white dark:bg-[#1A1D24] border border-border rounded-full flex items-center justify-center shadow-md hover:bg-muted z-20 transition-colors"
              title="Collapse panel"
            >
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
            <div className="h-full overflow-y-auto">
              {analysisState === 'complete' || location === '/report'
                ? <ReportPanel />
                : <GatePanel />}
            </div>
          </div>
        ) : (
          /* Collapsed right strip */
          <div className="relative w-11 flex-shrink-0 h-full border-l border-border bg-card/60 z-10 flex flex-col items-center justify-between py-6 shadow-[-2px_0_16px_rgba(0,0,0,0.03)]">
            <button
              onClick={() => setRightOpen(true)}
              className="w-8 h-8 rounded-full bg-primary/10 hover:bg-primary/20 flex items-center justify-center transition-colors"
              title="Expand panel"
            >
              <ChevronLeft className="w-3.5 h-3.5 text-primary" />
            </button>
            <div className="flex flex-col items-center gap-2">
              <FileText className="w-4 h-4 text-muted-foreground/50" />
              <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-widest leading-none" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>
                Report
              </p>
            </div>
            <div className="w-4 h-4" />
          </div>
        )
      )}

      {/* History full-screen overlay on desktop */}
      {location === '/history' && (
        <div className="absolute inset-0 z-20 bg-background/96 backdrop-blur-md overflow-y-auto">
          <div className="max-w-3xl mx-auto py-10 px-6 h-full">
            <HistoryPanel />
          </div>
        </div>
      )}
    </div>
  );
}
