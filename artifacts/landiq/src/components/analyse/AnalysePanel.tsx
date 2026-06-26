import { useState } from "react";
import { useLocation } from "wouter";
import { Play, UploadCloud, CheckCircle2, Loader2, X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useAppContext } from "@/context/AppContext";
import { useToast } from "@/hooks/use-toast";

const STEPS = [
  { label: "Normalizing coordinates…", pct: 30 },
  { label: "Running GIS analysis…", pct: 60 },
  { label: "Checking cadastral registry…", pct: 90 },
  { label: "Finalising extraction…", pct: 100 },
];

export function AnalysePanel() {
  const [, setLocation] = useLocation();
  const { setAnalysisState } = useAppContext();
  const { toast } = useToast();

  const [isExtracting, setIsExtracting] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [coordMode, setCoordMode] = useState<"DEC" | "DMS" | "UTM">("UTM");
  const [coordError, setCoordError] = useState<string | null>(null);
  const [coords, setCoords] = useState("");

  const handleExtract = () => {
    if (!coords.trim() && !uploadedFile) {
      setCoordError("Please upload a survey document or enter coordinates before proceeding.");
      toast({ title: "Missing input", description: "Upload a document or paste coordinates.", variant: "destructive" });
      return;
    }
    setCoordError(null);
    setIsExtracting(true);
    setAnalysisState("extracting");
    let idx = 0;

    const interval = setInterval(() => {
      idx++;
      setStepIdx(idx);
      if (idx >= STEPS.length - 1) {
        clearInterval(interval);
        setTimeout(() => {
          setIsExtracting(false);
          setAnalysisState("gate");
          setLocation("/gate");
          toast({ title: "Extraction complete", description: "Review and confirm the detected boundary." });
        }, 500);
      }
    }, 950);
  };

  const progress = isExtracting ? STEPS[Math.min(stepIdx, STEPS.length - 1)].pct : 0;
  const stepLabel = STEPS[Math.min(stepIdx, STEPS.length - 1)].label;

  return (
    <div className="p-5 flex flex-col h-full overflow-y-auto">
      <div className="mb-6">
        <h2 className="text-xl font-bold tracking-tight text-foreground">New Analysis</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Input parameters to verify land boundaries</p>
      </div>

      <div className="space-y-5 flex-1">

        {/* ① View As (Target Persona) — FIRST */}
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">View As (Target Persona)</Label>
          <Select defaultValue="buyer">
            <SelectTrigger className="bg-background h-11 text-sm">
              <SelectValue placeholder="Select persona" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="buyer">Everyday Land Buyer</SelectItem>
              <SelectItem value="planner">City Planner</SelectItem>
              <SelectItem value="engineer">Infrastructure Engineer</SelectItem>
              <SelectItem value="legal">Legal Practitioner</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* ② Stated Area (optional) */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Label htmlFor="area" className="text-xs font-semibold text-foreground">Stated Area (sqm)</Label>
            <span className="text-[9px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-medium">Optional</span>
          </div>
          <Input id="area" placeholder="e.g. 12000" type="number" className="bg-background h-11 text-sm" />
        </div>

        {/* ③ Survey Document upload */}
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">Survey Document</Label>
          {uploadedFile ? (
            <div className="flex items-center gap-3 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-xl p-3">
              <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
              <span className="text-xs font-medium text-green-700 dark:text-green-400 flex-1 truncate">{uploadedFile}</span>
              <button onClick={() => setUploadedFile(null)} className="text-green-600 hover:text-green-800">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <label className="border-2 border-dashed border-border rounded-xl p-5 flex flex-col items-center justify-center text-center bg-background/50 hover:bg-muted/30 hover:border-primary/40 transition-all cursor-pointer group block">
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 group-hover:bg-primary/20 transition-all">
                <UploadCloud className="w-4 h-4 text-primary" />
              </div>
              <p className="font-semibold text-sm text-foreground mb-0.5">Upload Survey Document</p>
              <p className="text-xs text-muted-foreground">Drag & drop or tap to browse</p>
              <p className="text-[10px] text-muted-foreground/60 mt-1">PDF, TXT, Image, XML or .zip</p>
              <input
                type="file"
                className="hidden"
                accept=".pdf,.txt,.xml,.zip,.jpg,.jpeg,.png"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) { setUploadedFile(f.name); setCoordError(null); }
                }}
              />
            </label>
          )}
        </div>

        {/* Divider */}
        <div className="relative flex items-center">
          <div className="flex-grow border-t border-border" />
          <span className="flex-shrink-0 mx-3 text-muted-foreground text-[10px] font-semibold uppercase tracking-wider">or enter manually</span>
          <div className="flex-grow border-t border-border" />
        </div>

        {/* ④ Geospatial Coordinates */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-semibold text-foreground">Geospatial Coordinates</Label>
            <div className="flex gap-1">
              {(["DEC", "DMS", "UTM"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setCoordMode(mode)}
                  className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded-md transition-colors ${
                    coordMode === mode ? "bg-primary text-white" : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
          <Textarea
            value={coords}
            onChange={(e) => { setCoords(e.target.value); setCoordError(null); }}
            placeholder={
              coordMode === "UTM"
                ? "Paste UTM vertices… e.g. 386804.297 550821.575 / 382852.590 550268.123 …"
                : coordMode === "DMS"
                ? "e.g. 6°31′27.8″N 3°22′45.1″E / …"
                : "e.g. 6.5244, 3.3792 / 6.5255, 3.3800 / …"
            }
            className={`font-mono text-xs min-h-[110px] bg-background resize-none leading-relaxed ${coordError ? "border-red-400 dark:border-red-600" : ""}`}
          />
          {coordError && (
            <p className="flex items-center gap-1.5 text-xs text-red-500">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />{coordError}
            </p>
          )}
          <p className="text-[10px] text-muted-foreground">Separate each point with a space or slash</p>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-5 space-y-3">
        {/* Cadastral status — always visible to show system readiness */}
        <div className="bg-muted/40 rounded-xl p-3 flex items-center justify-between border border-border/60">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse flex-shrink-0" />
            <span className="text-xs font-medium text-foreground">Cadastral Sub-system Active</span>
          </div>
          <Badge className="bg-primary/10 text-primary hover:bg-primary/10 text-[9px] border-none font-mono tracking-wide">OCR_TABLE</Badge>
        </div>

        {/* Progress bar — shows during extraction */}
        {isExtracting && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground truncate">{stepLabel}</p>
              <p className="text-xs font-bold text-primary tabular-nums">{progress}%</p>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        <Button
          className="w-full rounded-full h-12 text-sm font-bold shadow-md hover:shadow-lg transition-all"
          onClick={handleExtract}
          disabled={isExtracting}
        >
          {isExtracting ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Extracting…
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <Play className="w-3.5 h-3.5 fill-current" />
              Extract & Verify Boundary
            </span>
          )}
        </Button>
      </div>
    </div>
  );
}
