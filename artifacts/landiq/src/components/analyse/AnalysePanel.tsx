import { useState } from "react";
import { useLocation } from "wouter";
import { Play, UploadCloud, CheckCircle2, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useAppContext } from "@/context/AppContext";

export function AnalysePanel() {
  const [, setLocation] = useLocation();
  const { setAnalysisState } = useAppContext();
  const [isExtracting, setIsExtracting] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [coordMode, setCoordMode] = useState<'DEC' | 'DMS' | 'UTM'>('UTM');

  const steps = [
    "Normalizing coordinates...",
    "Running GIS analysis...",
    "Checking cadastral registry...",
  ];

  const handleExtract = () => {
    setIsExtracting(true);
    setAnalysisState('extracting');
    let step = 0;
    const interval = setInterval(() => {
      step++;
      setLoadingStep(step);
      if (step >= steps.length) {
        clearInterval(interval);
        setTimeout(() => {
          setIsExtracting(false);
          setAnalysisState('gate');
          setLocation('/gate');
        }, 600);
      }
    }, 900);
  };

  return (
    <div className="p-5 flex flex-col h-full overflow-y-auto">
      <div className="mb-5">
        <h2 className="text-xl font-bold tracking-tight text-foreground">New Analysis</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Input parameters to verify land boundaries</p>
      </div>

      <div className="space-y-5 flex-1">

        {/* ① Upload Survey Document — PRIMARY */}
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">Survey Document</Label>
          {uploadedFile ? (
            <div className="flex items-center gap-3 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-xl p-3">
              <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
              <span className="text-xs font-medium text-green-800 dark:text-green-400 flex-1 truncate">{uploadedFile}</span>
              <button onClick={() => setUploadedFile(null)} className="text-green-600 hover:text-green-800">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <label className="border-2 border-dashed border-border rounded-xl p-5 flex flex-col items-center justify-center text-center bg-background/50 hover:bg-muted/40 transition-colors cursor-pointer group block">
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 transition-transform">
                <UploadCloud className="w-4 h-4 text-primary" />
              </div>
              <p className="font-medium text-sm text-foreground mb-0.5">Upload Survey Document</p>
              <p className="text-xs text-muted-foreground">Drag & drop or tap to browse</p>
              <p className="text-[10px] text-muted-foreground/60 mt-1">PDF, TXT, Image, XML or .zip</p>
              <input
                type="file"
                className="hidden"
                accept=".pdf,.txt,.xml,.zip,.jpg,.jpeg,.png"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) setUploadedFile(f.name);
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

        {/* Stated Area */}
        <div className="space-y-1.5">
          <Label htmlFor="area" className="text-xs font-semibold text-foreground">Stated Area (HA)</Label>
          <Input id="area" placeholder="e.g. 1.20" type="number" className="bg-background h-10 text-sm" />
        </div>

        {/* Target Persona */}
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">View As (Target Persona)</Label>
          <Select defaultValue="buyer">
            <SelectTrigger className="bg-background h-10 text-sm">
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

        {/* ② Geospatial Coordinates — SECONDARY (the moat) */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-semibold text-foreground">Geospatial Coordinates</Label>
            <div className="flex gap-1">
              {(['DEC', 'DMS', 'UTM'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setCoordMode(mode)}
                  className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded-md transition-colors ${
                    coordMode === mode
                      ? 'bg-primary text-white'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
          <Textarea
            placeholder={
              coordMode === 'UTM'
                ? "Paste UTM vertices... e.g. 386804.297 550821.575 / 382852.590 550268.123 ..."
                : coordMode === 'DMS'
                ? "e.g. 6°31'27.8\"N 3°22'45.1\"E / ..."
                : "e.g. 6.5244, 3.3792 / 6.5255, 3.3800 / ..."
            }
            className="font-mono text-xs min-h-[110px] bg-background resize-none leading-relaxed"
          />
          <p className="text-[10px] text-muted-foreground">Separate each point with a space or slash</p>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-5 space-y-3">
        <div className="bg-muted/40 rounded-xl p-3 flex items-center justify-between border border-border/60">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse flex-shrink-0" />
            <span className="text-xs font-medium text-foreground">Cadastral Sub-system Active</span>
          </div>
          <Badge className="bg-primary/10 text-primary hover:bg-primary/10 text-[9px] border-none font-mono tracking-wide">OCR_TABLE</Badge>
        </div>

        <Button
          className="w-full rounded-full h-11 text-sm font-bold shadow-md hover:shadow-lg transition-all relative overflow-hidden"
          onClick={handleExtract}
          disabled={isExtracting}
        >
          {isExtracting ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              {steps[Math.min(loadingStep, steps.length - 1)]}
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
