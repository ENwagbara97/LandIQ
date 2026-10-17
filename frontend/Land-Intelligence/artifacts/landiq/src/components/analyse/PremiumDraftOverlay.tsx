import React from "react";
import { Sparkles, ChevronRight } from "lucide-react";

interface Props {
  closureErrorM: number;
  onExtract: () => void;
}

export function PremiumDraftOverlay({ closureErrorM, onExtract }: Props) {
  return (
    <div
      className="hidden absolute bottom-6 left-1/2 -translate-x-1/2 z-[150] w-[calc(100%-2rem)] max-w-sm pointer-events-auto"
      style={{ filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.35))" }}
    >
      <div className="rounded-2xl overflow-hidden border border-cyan-500/30 bg-[#0f172a]/95 backdrop-blur-md text-white">
        {/* Top accent bar */}
        <div className="h-1 w-full bg-gradient-to-r from-cyan-400 via-sky-400 to-cyan-400" />

        <div className="px-5 py-4 space-y-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-cyan-500/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-cyan-400" />
            </div>
            <div>
              <p className="text-sm font-bold text-white leading-tight">Geometry Verified &amp; Closed</p>
              <p className="text-[11px] text-cyan-300/80 font-medium mt-0.5">
                Closure error: <span className="text-cyan-300 font-bold">{closureErrorM.toFixed(3)}m</span>
              </p>
            </div>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed">
            The survey math closes correctly. To snap this boundary onto the live satellite imagery and check for property overlaps or structural conflicts, run your full verification report below.
          </p>

          <button
            onClick={onExtract}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 active:scale-95 transition-all text-sm font-semibold text-white py-2.5 px-4"
          >
            Extract &amp; Verify Boundary
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
