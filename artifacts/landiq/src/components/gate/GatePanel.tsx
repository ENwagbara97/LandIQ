import { useLocation } from "wouter";
import { Check, X, ArrowRight, FileSearch, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppContext } from "@/context/AppContext";

export function GatePanel() {
  const [, setLocation] = useLocation();
  const { setAnalysisState } = useAppContext();

  const handleConfirm = () => {
    setAnalysisState('complete');
    setLocation('/report');
  };

  const handleReject = () => {
    setAnalysisState(null);
    setLocation('/analyse');
  };

  return (
    <div className="p-6 flex flex-col h-full animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="mb-6">
        <h2 className="text-2xl font-bold tracking-tight mb-2">Verify Extraction</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Please confirm the detected geometry is accurate before analytical run.
        </p>
      </div>

      <div className="space-y-6 flex-1">
        {/* Plan Metadata */}
        <div className="bg-background rounded-xl border border-border p-4 shadow-sm">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <FileSearch className="w-3.5 h-3.5" /> Plan Metadata
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-[10px] text-muted-foreground uppercase mb-0.5">Owner</p>
              <p className="text-sm font-medium">Unknown</p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase mb-0.5">Location</p>
              <p className="text-sm font-medium">Not specified</p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase mb-0.5">Datum</p>
              <p className="text-sm font-medium">MINNA</p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase mb-0.5">Plan No</p>
              <p className="text-sm font-medium">Unknown</p>
            </div>
          </div>
        </div>

        {/* Coordinate Health Check */}
        <div className="bg-background rounded-xl border border-border p-4 shadow-sm">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">Coordinate Health Check</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Closed Polygon</span>
              <span className="font-medium flex items-center text-green-600 dark:text-green-500"><Check className="w-3 h-3 mr-1" /> Yes</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Closure Error</span>
              <span className="font-medium flex items-center text-green-600 dark:text-green-500"><Check className="w-3 h-3 mr-1" /> 0.00m</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Beacon Count</span>
              <span className="font-medium flex items-center text-green-600 dark:text-green-500"><Check className="w-3 h-3 mr-1" /> 5 beacons</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">No Self-Intersection</span>
              <span className="font-medium flex items-center text-green-600 dark:text-green-500"><Check className="w-3 h-3 mr-1" /> Passed</span>
            </div>
          </div>
        </div>

        {/* Area Verification */}
        <div className="bg-background rounded-xl border border-border p-4 shadow-sm">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">Area Verification</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Stated Area</span>
              <span className="font-medium">Not stated</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Computed</span>
              <span className="font-medium">1,348,164 sqm <span className="text-muted-foreground text-xs ml-1">(2080.5 plots)</span></span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Area</span>
              <span className="font-medium">134.82 ha</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Discrepancy</span>
              <span className="font-medium text-muted-foreground">--</span>
            </div>
          </div>
        </div>

        <Button variant="outline" className="w-full">
          Review Technical Details (Ledger)
        </Button>
      </div>

      <div className="mt-8 flex gap-3">
        <Button 
          variant="outline" 
          className="flex-1 rounded-full h-12 text-destructive border-destructive/30 hover:bg-destructive/10 hover:text-destructive"
          onClick={handleReject}
        >
          <X className="w-4 h-4 mr-2" /> Reject
        </Button>
        <Button 
          className="flex-1 rounded-full h-12 bg-primary hover:bg-primary/90 text-white shadow-md hover:shadow-lg transition-all"
          onClick={handleConfirm}
        >
          <Check className="w-4 h-4 mr-2" /> Confirm
        </Button>
      </div>
    </div>
  );
}
