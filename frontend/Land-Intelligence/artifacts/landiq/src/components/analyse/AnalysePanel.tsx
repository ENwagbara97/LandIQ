import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "wouter";
import { Play, UploadCloud, FileUp, CheckCircle2, Loader2, X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useAppContext } from "@/context/AppContext";
import { useToast } from "@/hooks/use-toast";
import { CogoTraverseGrid, COGOPayload } from "./CogoTraverseGrid";
import { CrsCorrectionModal } from "../gate/CrsCorrectionModal";
import { cn } from "@/lib/utils";
import { apiUrl } from "@/lib/api";

const STEPS = [
  { label: "Normalizing coordinates…", pct: 30 },
  { label: "Running GIS analysis…", pct: 60 },
  { label: "Checking cadastral registry…", pct: 90 },
  { label: "Finalising extraction…", pct: 100 },
];

export function AnalysePanel() {
  const [, setLocation] = useLocation();
  const { analysisState, setAnalysisState, setSessionId, setParcelCoords, formData, setFormData, extractTriggerRef } = useAppContext();
  const { toast } = useToast();

  const areaInputRef = useRef<HTMLInputElement>(null);
  const coordsInputRef = useRef<HTMLTextAreaElement>(null);

  const [isExtracting, setIsExtracting] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  const [coordError, setCoordError] = useState<string | null>(null);
  const [cogoPayload, setCogoPayload] = useState<COGOPayload | null>(null);
  // ocrMode removed — OCR provider routing is handled server-side automatically
  const [personasConfig, setPersonasConfig] = useState<{id: string, label: string, desc: string}[]>([]);
  const [crsModalOpen, setCrsModalOpen] = useState(false);

  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) {
      setUploadedFile(f);
      setCoordError(null);
    }
  };

  const { file: uploadedFile, coordMode, coordinates: coords, area: statedAreaSqm, persona } = formData;
  
  const setUploadedFile = (f: File | null) => setFormData(prev => ({ ...prev, file: f }));
  const setCoordMode = (mode: "text" | "cogo") => setFormData(prev => ({ ...prev, coordMode: mode }));
  const setCoords = (c: string) => setFormData(prev => ({ ...prev, coordinates: c }));
  const setStatedAreaSqm = (a: string) => setFormData(prev => ({ ...prev, area: a }));
  const setPersona = (p: string) => setFormData(prev => ({ ...prev, persona: p }));
  
  // user_id: use localStorage to persist a stable anonymous ID per device
  const [userId] = useState<string>(() => {
    const stored = localStorage.getItem("landiq_user_id");
    if (stored) return stored;
    const id = `user-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("landiq_user_id", id);
    return id;
  });

  useEffect(() => {
    fetch(apiUrl("/api/config/personas"))
      .then(r => r.json())
      .then(data => setPersonasConfig(data))
      .catch(() => {
        setPersonasConfig([
          { id: "EVERYDAY_BUYER", label: "Land buyer", desc: "" },
          { id: "SURVEYOR", label: "Surveyor", desc: "" },
          { id: "REALTOR", label: "Realtor", desc: "" },
          { id: "ARCHITECT", label: "Architect", desc: "" },
          { id: "DEVELOPER", label: "Developer", desc: "" },
          { id: "LEGAL_PRACTITIONER", label: "Legal practitioner", desc: "" },
          { id: "ESTATE_VALUER", label: "Estate valuer", desc: "" },
          { id: "OTHERS", label: "Others", desc: "" }
        ]);
      });
  }, []);

  const handleExtract = async () => {
    if (!statedAreaSqm || !statedAreaSqm.trim()) {
      toast({ title: "Missing input", description: "The stated area is required for verification. Please enter it.", variant: "destructive" });
      areaInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      areaInputRef.current?.focus();
      return;
    }
    if (!coords.trim() && !uploadedFile && coordMode !== "cogo") {
      setCoordError("Please upload a survey document or enter coordinates before proceeding.");
      toast({ title: "Missing input", description: "Upload a document or paste coordinates.", variant: "destructive" });
      coordsInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      coordsInputRef.current?.focus();
      return;
    }
    setCoordError(null);

    // --- CRS Confirmation Gate ---
    const hasCrsHeader = coords.includes("# CRS:");
    const isTextBasedFile = (() => {
      if (!uploadedFile) return false;
      const ext = uploadedFile.name.split(".").pop()?.toLowerCase() ?? "";
      return ["txt", "csv", "xls", "xlsx"].includes(ext);
    })();

    const needsCrsConfirm =
      coordMode !== "cogo" &&
      (
        (coordMode === "text" && coords.trim() && !hasCrsHeader && !uploadedFile) ||
        isTextBasedFile
      );

    if (needsCrsConfirm) {
      setCrsModalOpen(true);
      return;
    }

    doExecuteExtraction();
  };

  // Wire the ref so MapView can call handleExtract programmatically
  useEffect(() => {
    if (extractTriggerRef) {
      extractTriggerRef.current = handleExtract;
    }
  });

  // Runs the actual API call. Accepts an optional CRS header string
  // that gets prepended to raw_text so the backend parses the right zone.
  const doExecuteExtraction = async (crsHeader?: string) => {
    setIsExtracting(true);
    setAnalysisState("extracting");
    setStepIdx(0);

    try {
      // Simulate progress visually while we wait for the network request
      const progressInterval = setInterval(() => {
        setStepIdx(prev => Math.min(prev + 1, STEPS.length - 2));
      }, 800);

      const formData = new FormData();
      if (coordMode === "cogo") {
        if (!cogoPayload) {
          throw new Error("Invalid COGO Traverse data. Please check your starting coordinates and traverse legs.");
        }
        formData.append("cogo_payload", JSON.stringify(cogoPayload));
      } else if (coords.trim()) {
        // Prepend the confirmed CRS header if the user selected one
        const textToSend = crsHeader ? `${crsHeader}\n${coords}` : coords;
        formData.append("raw_text", textToSend);
      }
      // Phase 5: use React state — no DOM scraping
      if (statedAreaSqm) {
        formData.append("stated_area_ha", (parseFloat(statedAreaSqm) / 10000).toString());
      }
      formData.append("persona_mode", persona || "EVERYDAY_BUYER");
      // Send stable user_id so history is scoped correctly
      formData.append("user_id", userId);
      // ocrMode removed — server handles OCR routing automatically
      
      // Load backend config seamlessly without user input
      const storedVisionProvider = localStorage.getItem("landiq_vision_provider") || "";
      const storedVisionApiKey   = localStorage.getItem("landiq_vision_api_key") || "";
      if (storedVisionProvider) {
        formData.append("vision_provider", storedVisionProvider);
        if (storedVisionApiKey) formData.append("vision_api_key", storedVisionApiKey);
      }
      // Attach file if one was uploaded
      if (uploadedFile) {
        formData.append("file", uploadedFile);
      }

      const response = await fetch(apiUrl("/api/upload"), {
        method: "POST",
        body: formData,
      });

      clearInterval(progressInterval);
      setStepIdx(STEPS.length - 1); // final step

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const errMsg = errorData?.detail?.message || errorData?.detail?.instruction || errorData?.detail || errorData?.message || "Failed to process coordinates";
        throw new Error(typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg));
      }

      const data = await response.json();
      console.log("Upload Response:", data);

      // P2 FIX: read normalized run_id first, fallback to legacy session_id fields
      const resolvedRunId =
        data.run_id ||
        data.session_id ||
        data.cad_result?.run_id ||
        null;
      if (resolvedRunId) {
        setSessionId(resolvedRunId);
      }

      // Store the real polygon coordinates for the map to render
      const rawCoords: number[][] = data.cad_result?.wgs84_polygon ||
        data.cad_result?.coordinates_wgs84 ||
        data.cad_result?.polygon?.wgs84_coordinates ||
        data.coordinates_wgs84 ||
        [];
      if (rawCoords.length > 0) {
        // Backend returns [lat, lng] pairs
        setParcelCoords(rawCoords.map((pt: number[]) => [pt[0], pt[1]] as [number, number]));
      }

      setTimeout(() => {
        setIsExtracting(false);
        setAnalysisState("gate");
        setLocation("/gate");
        toast({ title: "Extraction complete", description: "Review and confirm the detected boundary." });
      }, 500);

    } catch (err: any) {
      setIsExtracting(false);
      setAnalysisState(null);
      const errMsg = err.message || "An error occurred during extraction.";
      setCoordError(errMsg);

      // F1 FIX: On OCR/coord failure, auto-open manual entry with actionable tips
      const isCoordFailure =
        errMsg.includes("NO_COORDINATES") ||
        errMsg.includes("INVALID_POLYGON") ||
        errMsg.includes("coordinates in this document") ||
        errMsg.includes("enough boundary points") ||
        errMsg.includes("300 DPI");

      if (isCoordFailure) {
        setCoordMode("text"); // Switch to manual text entry
        toast({
          title: "Could not read plan automatically",
          description:
            "Tips: scan at 300 DPI+, upload PDF not a photo, or enter coordinates manually below.",
          variant: "destructive",
          duration: 8000,
        });
      } else {
        toast({ title: "Extraction Failed", description: errMsg, variant: "destructive" });
      }
    }
  };

  const progress = isExtracting ? STEPS[Math.min(stepIdx, STEPS.length - 1)].pct : 0;
  const stepLabel = STEPS[Math.min(stepIdx, STEPS.length - 1)].label;

  return (
    <div className="px-5 pt-5 pb-10 flex flex-col">
      {/* Full-screen Extraction Overlay (Portaled to break out of sidebar) */}
      {isExtracting && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 animate-in fade-in duration-300">
          <div className="bg-background border border-border/60 rounded-2xl p-5 shadow-2xl w-full max-w-sm space-y-4 animate-in zoom-in-95 duration-300">
            <div className="flex items-center justify-center mb-2">
              <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center">
                <Loader2 className="w-6 h-6 text-primary animate-spin" />
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-foreground truncate">{stepLabel}</p>
                <p className="text-sm font-bold text-primary tabular-nums">{progress}%</p>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
            <p className="text-xs text-center text-muted-foreground pt-1">
              Please wait while we verify cadastral records...
            </p>
          </div>
        </div>,
        document.body
      )}

      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-bold tracking-tight text-foreground">New Analysis</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Input parameters to verify land boundaries</p>
      </div>

      <div className="space-y-5 pb-6">

        {/* ① View As (Target Persona) — FIRST */}
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">View As (Target Persona)</Label>
          <Select value={persona} onValueChange={setPersona}>
            <SelectTrigger className="bg-background h-11 text-sm">
              <SelectValue placeholder="Select persona" />
            </SelectTrigger>
            <SelectContent>
              {personasConfig.length > 0 ? personasConfig.map(p => (
                <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>
              )) : (
                <SelectItem value="EVERYDAY_BUYER">Everyday Land Buyer</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>

        {/* ② Stated Area */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Label htmlFor="area" className="text-xs font-semibold text-foreground">Stated Area (sqm) <span className="text-destructive">*</span></Label>
          </div>
          <Input
            id="area"
            ref={areaInputRef}
            placeholder="e.g. 12000"
            type="number"
            className="bg-background h-11 text-sm"
            value={statedAreaSqm}
            onChange={e => setStatedAreaSqm(e.target.value)}
          />
        </div>

        {/* ③ Survey Document upload */}
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">Survey Document</Label>
          {uploadedFile ? (
            <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-3.5 transition-all">
              <div className="w-8 h-8 rounded-xl bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center flex-shrink-0">
                <FileUp className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-foreground truncate">{uploadedFile.name}</p>
                <p className="text-[10px] text-muted-foreground">
                  {(uploadedFile.size / 1024).toFixed(1)} KB · Ready for OCR
                </p>
              </div>
              <button
                type="button"
                onClick={() => setUploadedFile(null)}
                className="p-1 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                title="Remove file"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <label
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                "relative border-2 border-dashed rounded-2xl p-6 flex flex-col items-center justify-center text-center transition-all duration-200 cursor-pointer group block overflow-hidden",
                isDragging
                  ? "border-primary bg-primary/10 shadow-[0_0_20px_rgba(220,38,38,0.15)] ring-2 ring-primary/20 scale-[1.01]"
                  : "border-border/80 bg-card/40 hover:bg-card hover:border-primary/50 hover:shadow-sm"
              )}
            >
              {/* Inner wrapper with pointer-events-none prevents child elements from triggering dragLeave flickering */}
              <div className="pointer-events-none flex flex-col items-center justify-center">
                <div className="w-11 h-11 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-3 text-primary group-hover:scale-105 group-hover:bg-primary group-hover:text-primary-foreground group-hover:border-primary transition-all duration-300 shadow-sm">
                  <FileUp className="w-5 h-5" />
                </div>
                <p className="font-semibold text-sm text-foreground mb-1 group-hover:text-primary transition-colors">
                  Upload Survey Document
                </p>
                <p className="text-xs text-muted-foreground hidden sm:block">
                  {isDragging ? "Drop your survey file here to analyze!" : "Drag & drop or click to browse"}
                </p>
                <p className="text-xs text-muted-foreground sm:hidden">Tap to browse or take a photo</p>
                <span className="inline-flex items-center gap-1 mt-2 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium text-muted-foreground/80 bg-muted/60 border border-border/40">
                  PDF · Image · TXT · XML · ZIP
                </span>
              </div>
              <input
                type="file"
                className="hidden"
                accept=".pdf,.txt,.xml,.zip,.jpg,.jpeg,.png,.heic,image/*"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) { setUploadedFile(f); setCoordError(null); }
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
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-semibold text-foreground">Geospatial Input Method</Label>
          </div>
          
          <div className="flex p-1 bg-muted dark:bg-[#1A1D24] rounded-full gap-1 border border-border/40">
            {(["text", "cogo"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setCoordMode(mode)}
                className={cn(
                  "flex-1 py-2.5 px-3 rounded-full text-xs font-semibold transition-all duration-200",
                  coordMode === mode
                    ? "bg-white dark:bg-[#0058BD] shadow-sm text-foreground dark:text-white"
                    : "text-muted-foreground hover:text-foreground dark:hover:text-white/80"
                )}
              >
                {mode === "text" ? "Paste Text" : "COGO Traverse"}
              </button>
            ))}
          </div>
          
          {coordMode === "cogo" ? (
            <CogoTraverseGrid onPayloadChange={setCogoPayload} />
          ) : (
            <>
              <Textarea
                ref={coordsInputRef}
                value={coords}
                onChange={(e) => { setCoords(e.target.value); setCoordError(null); }}
                placeholder="Paste coordinates here... e.g. 6.5244, 3.3792 / 6°31′27″N 3°22′45″E / 386804.297 550821.575"
                className={`font-mono text-xs min-h-[110px] bg-background resize-none leading-relaxed ${coordError ? "border-red-400 dark:border-red-600" : ""}`}
              />
              {coordError && (
                <p className="flex items-center gap-1.5 text-xs text-red-500">
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />{coordError}
                </p>
              )}
              <p className="text-[10px] text-muted-foreground">Separate each point with a space or slash</p>
            </>
          )}
        </div>
      </div>

      {/* Footer / Debug Options Removed for Production Simplicity */}
      <div className="mt-2 space-y-3">
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

      {/* CRS Confirmation Modal — shown before extraction when user pastes raw coords */}
      <CrsCorrectionModal
        isOpen={crsModalOpen}
        title="Confirm Coordinate Reference System"
        message="Your pasted coordinates don't carry a CRS tag. Please select the correct zone so the boundary lands in the right location."
        currentCrs="UTM Zone 32N (WGS84)"
        onSelectZone={(epsg, name) => {
          setCrsModalOpen(false);
          doExecuteExtraction(`# CRS: ${name} (EPSG:${epsg})`);
        }}
        onClose={() => setCrsModalOpen(false)}
      />
    </div>
  );
}
