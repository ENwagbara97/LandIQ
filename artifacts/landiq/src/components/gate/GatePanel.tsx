import { useState } from "react";
import { useLocation } from "wouter";
import { Check, X, ChevronDown, ChevronUp, RefreshCw, Table2 } from "lucide-react";
import { useAppContext } from "@/context/AppContext";

const ledgerData = [
  { id: "S1", easting: "378829.130", northing: "500331.230", source: "Stated" },
  { id: "S2", easting: "378630.280", northing: "500291.080", source: "Stated" },
  { id: "S3", easting: "378597.780", northing: "500403.890", source: "Stated" },
  { id: "S4", easting: "378798.540", northing: "500447.860", source: "Stated" },
  { id: "S1(close)", easting: "378829.130", northing: "500331.230", source: "Stated" },
];

function HealthRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-[#1E2D3D]/60 last:border-0">
      <span className="text-[#7A8FA0] text-sm">{label}</span>
      <span className="flex items-center gap-1.5 text-[#3DD68C] text-sm font-semibold">
        <Check className="w-3.5 h-3.5" strokeWidth={3} />
        {value}
      </span>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-[#4A6070] uppercase tracking-wider font-semibold mb-0.5">{label}</p>
      <p className="text-[#C8D8E8] text-sm font-medium">{value}</p>
    </div>
  );
}

export function GatePanel() {
  const [, setLocation] = useLocation();
  const { setAnalysisState } = useAppContext();
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  const handleConfirm = () => {
    setAnalysisState('complete');
    setLocation('/report');
  };

  const handleReject = () => {
    setAnalysisState(null);
    setLocation('/analyse');
  };

  const handleRecompute = () => {
    setRecomputing(true);
    setTimeout(() => setRecomputing(false), 1800);
  };

  return (
    <div
      className="flex flex-col h-full overflow-y-auto text-white"
      style={{ background: 'linear-gradient(180deg, #0D1523 0%, #0F1A2B 100%)' }}
    >
      {/* Header */}
      <div className="px-5 pt-6 pb-5 flex-shrink-0">
        <h2 className="text-xl font-bold text-white tracking-tight mb-1">Verify Extraction</h2>
        <p className="text-[#7A8FA0] text-xs leading-relaxed">
          Please confirm the detected geometry is accurate before analytical run.
        </p>
      </div>

      <div className="flex-1 px-4 space-y-3 pb-4">

        {/* Plan Metadata */}
        <div className="bg-[#131F30] rounded-2xl border border-[#1E2D3D] p-4">
          <p className="text-[10px] font-bold text-[#4A6070] uppercase tracking-widest mb-3">Plan Metadata</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <MetaRow label="Owner" value="Unknown" />
            <MetaRow label="Location" value="Not specified" />
            <MetaRow label="Datum" value="MINNA" />
            <MetaRow label="Plan No" value="Unknown" />
          </div>
        </div>

        {/* Coordinate Health Check */}
        <div className="bg-[#131F30] rounded-2xl border border-[#1E2D3D] p-4">
          <p className="text-[10px] font-bold text-[#4A6070] uppercase tracking-widest mb-2">Coordinate Health Check</p>
          <HealthRow label="Closed Polygon" value="Yes" />
          <HealthRow label="Closure Error" value="0.00m" />
          <HealthRow label="Beacon Count" value="4 beacons" />
          <HealthRow label="No Self-Intersection" value="Passed" />
        </div>

        {/* Area Verification */}
        <div className="bg-[#131F30] rounded-2xl border border-[#1E2D3D] p-4">
          <p className="text-[10px] font-bold text-[#4A6070] uppercase tracking-widest mb-3">Area Verification</p>
          <div className="space-y-2.5">
            <div className="flex justify-between items-baseline">
              <span className="text-[#7A8FA0] text-sm">Stated Area</span>
              <span className="text-[#C8D8E8] text-sm font-medium">Not stated</span>
            </div>
            <div className="flex justify-between items-baseline gap-4">
              <span className="text-[#7A8FA0] text-sm flex-shrink-0">Computed Area</span>
              <span className="text-[#C8D8E8] text-sm font-medium text-right">
                24,248 sqm
                <span className="text-[#4A6070] text-xs ml-1 block">≈ 37.4 plots · 2.42 ha</span>
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-[#7A8FA0] text-sm">Discrepancy</span>
              <span className="text-[#4A6070] text-sm">--</span>
            </div>
          </div>
        </div>

        {/* Ledger Toggle */}
        <button
          onClick={() => setLedgerOpen(v => !v)}
          className="w-full flex items-center justify-between bg-[#131F30] rounded-2xl border border-[#1E2D3D] px-4 py-3.5 text-left hover:border-[#0058BD]/40 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <Table2 className="w-4 h-4 text-[#0058BD]" />
            <span className="text-sm font-medium text-[#C8D8E8]">Review Technical Details (Ledger)</span>
          </div>
          {ledgerOpen
            ? <ChevronUp className="w-4 h-4 text-[#4A6070]" />
            : <ChevronDown className="w-4 h-4 text-[#4A6070]" />}
        </button>

        {/* Coordinate Ledger Table */}
        {ledgerOpen && (
          <div className="bg-[#0A1120] rounded-2xl border border-[#1E2D3D] overflow-hidden">
            <p className="text-[10px] font-bold text-[#4A6070] uppercase tracking-widest px-4 pt-3 pb-2">Coordinate Ledger</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[360px]">
                <thead>
                  <tr className="border-b border-[#1E2D3D]">
                    {["Station ID", "Easting (M)", "Northing (M)", "Source"].map(h => (
                      <th key={h} className="text-left px-4 py-2 text-[9px] font-bold text-[#4A6070] uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ledgerData.map((row, i) => (
                    <tr key={i} className="border-b border-[#1E2D3D]/40 last:border-0">
                      <td className="px-4 py-2.5 text-xs font-mono text-[#0058BD]">{row.id}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-[#C8D8E8]">{row.easting}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-[#C8D8E8]">{row.northing}</td>
                      <td className="px-4 py-2.5 text-xs text-[#7A8FA0]">{row.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Recompute Button */}
        <button
          onClick={handleRecompute}
          disabled={recomputing}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl border border-[#0058BD]/40 bg-[#0058BD]/10 text-[#5B9BF5] text-sm font-semibold hover:bg-[#0058BD]/20 transition-all disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${recomputing ? 'animate-spin' : ''}`} />
          {recomputing ? "Recomputing..." : "Recompute Polygon"}
        </button>
      </div>

      {/* Action Buttons — sticky bottom */}
      <div className="flex-shrink-0 px-4 pt-3 pb-6 border-t border-[#1E2D3D] bg-[#0D1523] flex gap-3">
        <button
          onClick={handleReject}
          className="flex-1 h-12 rounded-full border border-[#EF4444]/40 bg-[#EF4444]/8 text-[#F87171] text-sm font-bold flex items-center justify-center gap-2 hover:bg-[#EF4444]/15 transition-all active:scale-[0.98]"
        >
          <X className="w-4 h-4" strokeWidth={2.5} /> Reject
        </button>
        <button
          onClick={handleConfirm}
          className="flex-1 h-12 rounded-full bg-[#0058BD] text-white text-sm font-bold flex items-center justify-center gap-2 hover:bg-[#0047A3] shadow-lg hover:shadow-[#0058BD]/30 transition-all active:scale-[0.98]"
        >
          <Check className="w-4 h-4" strokeWidth={2.5} /> Confirm
        </button>
      </div>
    </div>
  );
}
