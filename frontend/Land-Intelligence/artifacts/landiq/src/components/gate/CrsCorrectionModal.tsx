import { useState } from "react";
import { createPortal } from "react-dom";
import { Compass, CheckCircle2 } from "lucide-react";

interface CrsCorrectionModalProps {
  isOpen: boolean;
  title?: string;
  message?: string;
  currentCrs?: string;
  onSelectZone: (epsg: number, zoneName: string) => void;
  onClose: () => void;
}

const ZONES = [
  { name: "UTM Zone 32N (WGS84)", epsg: 32632, region: "Central & SE Nigeria (Abuja, Rivers, Akwa Ibom, Uyo, Enugu)" },
  { name: "UTM Zone 31N (WGS84)", epsg: 32631, region: "Western Nigeria (Lagos, Ogun, Oyo, Kwara, Niger West)" },
  { name: "UTM Zone 33N (WGS84)", epsg: 32633, region: "Far Northeast (Borno East, Yobe East, Adamawa)" },
  { name: "Minna Datum (Clarke 1880)", epsg: 26332, region: "Legacy Nigerian National Datum (1970s Paper Surveys)" },
];

export function CrsCorrectionModal({
  isOpen,
  title = "Confirm Coordinate Reference System",
  message,
  currentCrs = "UTM Zone 32N (WGS84)",
  onSelectZone,
  onClose,
}: CrsCorrectionModalProps) {
  // Track which zone the user has highlighted — defaults to Zone 32N
  const defaultZone = ZONES.find(z => currentCrs.includes(z.name) || currentCrs.includes(z.epsg.toString())) ?? ZONES[0];
  const [selected, setSelected] = useState(defaultZone);

  if (!isOpen) return null;

  const modal = (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-card border border-border max-w-md w-full rounded-3xl p-6 shadow-2xl space-y-5">

        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="p-3 bg-primary/10 text-primary rounded-2xl flex-shrink-0">
            <Compass className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-foreground">{title}</h3>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {message ?? "Your coordinates don't carry a CRS tag. Select the correct zone so the boundary lands in the right location."}
            </p>
          </div>
        </div>

        {/* Zone List */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Select Correct Coordinate Reference System (CRS):
          </p>

          <div className="space-y-2">
            {ZONES.map((z) => {
              const isSelected = selected.epsg === z.epsg;
              return (
                <button
                  key={z.epsg}
                  onClick={() => setSelected(z)}
                  className={`w-full text-left p-3.5 rounded-2xl border transition-all flex items-center justify-between group ${
                    isSelected
                      ? "bg-primary/10 border-primary/50 text-foreground"
                      : "bg-background hover:bg-muted border-border text-foreground/80"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Compass className={`w-4 h-4 transition-transform group-hover:scale-110 ${isSelected ? "text-primary" : "text-muted-foreground"}`} />
                    <div>
                      <div className={`text-xs font-bold ${isSelected ? "text-foreground" : ""}`}>
                        {z.name}{" "}
                        <span className="text-[10px] font-mono text-muted-foreground">({z.epsg})</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground">{z.region}</div>
                    </div>
                  </div>
                  {isSelected && <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />}
                </button>
              );
            })}
          </div>
        </div>

        {/* Footer: Dismiss + Choose */}
        <div className="pt-1 flex items-center justify-between gap-3">
          <button
            onClick={onClose}
            className="flex-1 h-10 rounded-full border border-border text-xs font-bold text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
          >
            Dismiss
          </button>
          <button
            onClick={() => {
              onSelectZone(selected.epsg, selected.name);
              onClose();
            }}
            className="flex-1 h-10 rounded-full bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 shadow-md transition-all active:scale-[0.98]"
          >
            Choose
          </button>
        </div>

      </div>
    </div>
  );

  // Portal to document.body so the overlay is always truly centered
  // regardless of which sidebar/panel renders it
  return createPortal(modal, document.body);
}
