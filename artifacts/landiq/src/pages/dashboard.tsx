import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { Drawer } from "vaul";
import { useAppContext } from "@/context/AppContext";
import { MapView } from "@/components/map/MapView";
import { AnalysePanel } from "@/components/analyse/AnalysePanel";
import { GatePanel } from "@/components/gate/GatePanel";
import { ReportPanel } from "@/components/report/ReportPanel";
import { HistoryPanel } from "@/components/history/HistoryPanel";
import { useMobile } from "@/hooks/use-mobile";

export function Dashboard() {
  const [location] = useLocation();
  const { analysisState, activeTab, setActiveTab } = useAppContext();
  const isMobile = useMobile();

  // Desktop view: Left Sidebar (Analyse) + Map + Right Sidebar (Gate/Report)
  // Mobile view: Full Map + Bottom Sheet for active tab

  if (isMobile) {
    return (
      <div className="relative w-full h-full flex flex-col">
        <div className="flex-1 relative">
           <MapView />
        </div>
        
        <Drawer.Root 
          open={location === '/analyse' || location === '/gate' || location === '/report' || location === '/history'}
          onOpenChange={(open) => {
            if (!open) window.history.back();
          }}
          snapPoints={[0.5, 1]}
          activeSnapPoint={1}
        >
          <Drawer.Portal>
            <Drawer.Overlay className="fixed inset-0 bg-black/40 z-50" />
            <Drawer.Content className="bg-background flex flex-col rounded-t-[28px] mt-24 h-[90vh] fixed bottom-0 left-0 right-0 z-50 shadow-2xl border-t border-border">
              <div className="p-4 bg-background rounded-t-[28px] flex-1 overflow-y-auto pb-24">
                <div className="mx-auto w-12 h-1.5 flex-shrink-0 rounded-full bg-muted mb-6" />
                {location === '/analyse' && <AnalysePanel />}
                {location === '/gate' && <GatePanel />}
                {location === '/report' && <ReportPanel />}
                {location === '/history' && <HistoryPanel />}
              </div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      </div>
    );
  }

  return (
    <div className="flex w-full h-full relative overflow-hidden bg-background">
      {/* Left Sidebar - Analyse */}
      <div className="w-[380px] h-full flex-shrink-0 border-r border-border bg-card/50 backdrop-blur-md overflow-y-auto z-10 shadow-[4px_0_24px_rgba(0,0,0,0.02)]">
        <AnalysePanel />
      </div>

      {/* Center - Map */}
      <div className="flex-1 relative z-0">
        <MapView />
      </div>

      {/* Right Sidebar - Gate / Report */}
      {(location === '/gate' || location === '/report' || analysisState === 'gate' || analysisState === 'complete') && (
        <div className="w-[420px] h-full flex-shrink-0 border-l border-border bg-card/50 backdrop-blur-md overflow-y-auto z-10 shadow-[-4px_0_24px_rgba(0,0,0,0.02)]">
           {location === '/report' || analysisState === 'complete' ? <ReportPanel /> : <GatePanel />}
        </div>
      )}

      {/* Full screen history overlay on desktop if accessed directly */}
      {location === '/history' && (
        <div className="absolute inset-0 z-20 bg-background/95 backdrop-blur-md overflow-y-auto p-8 flex justify-center">
           <div className="max-w-4xl w-full">
             <HistoryPanel />
           </div>
        </div>
      )}
    </div>
  );
}
