import { useState } from "react";
import { useLocation } from "wouter";
import { Play, UploadCloud, CheckCircle2, ChevronRight, Loader2 } from "lucide-react";
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

  const steps = [
    "Normalizing coordinates...",
    "Running GIS analysis...",
    "Checking cadastral registry..."
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
        }, 500);
      }
    }, 800);
  };

  return (
    <div className="p-6 flex flex-col h-full">
      <div className="mb-6">
        <h2 className="text-2xl font-bold tracking-tight mb-1">New Analysis</h2>
        <p className="text-sm text-muted-foreground">Input parameters to verify land boundaries</p>
      </div>

      <div className="space-y-6 flex-1">
        <div className="space-y-2">
          <Label htmlFor="area">Stated Area (HA)</Label>
          <Input id="area" placeholder="e.g. 1.20" type="number" className="bg-background" />
        </div>

        <div className="space-y-2">
          <Label>View As (Target Persona)</Label>
          <Select defaultValue="buyer">
            <SelectTrigger className="bg-background">
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

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <Label>Geospatial Coordinates</Label>
            <div className="flex gap-1">
              <Badge variant="secondary" className="text-[10px] cursor-pointer hover:bg-muted font-mono">DEC</Badge>
              <Badge variant="outline" className="text-[10px] cursor-pointer hover:bg-muted font-mono">DMS</Badge>
              <Badge variant="outline" className="text-[10px] cursor-pointer hover:bg-muted font-mono">UTM</Badge>
            </div>
          </div>
          <Textarea 
            placeholder="Paste polygon vertices or boundary points... e.g. 386804.297 550821.575 / 382852.590 550268.123 ..."
            className="font-mono text-xs min-h-[120px] bg-background resize-none"
          />
        </div>

        <div className="relative flex items-center py-2">
          <div className="flex-grow border-t border-border"></div>
          <span className="flex-shrink-0 mx-4 text-muted-foreground text-xs font-medium uppercase">OR</span>
          <div className="flex-grow border-t border-border"></div>
        </div>

        <div className="border-2 border-dashed border-border rounded-xl p-6 flex flex-col items-center justify-center text-center bg-background/50 hover:bg-muted/50 transition-colors cursor-pointer group">
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
            <UploadCloud className="w-5 h-5 text-primary" />
          </div>
          <h4 className="font-medium text-sm mb-1">Upload Survey Document</h4>
          <p className="text-xs text-muted-foreground mb-2">Drag and drop or click to browse</p>
          <p className="text-[10px] text-muted-foreground/70">Supports TXT, PDF, image, XML or .zip</p>
        </div>
      </div>

      <div className="mt-8 space-y-4">
        <div className="bg-muted/50 rounded-lg p-3 flex items-center justify-between border border-border/50">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs font-medium text-foreground">Cadastral Sub-system Active</span>
          </div>
          <Badge className="bg-primary/10 text-primary hover:bg-primary/20 text-[10px] border-none">OCR_TABLE</Badge>
        </div>

        <Button 
          className="w-full rounded-full h-12 text-base font-bold shadow-lg hover:shadow-xl transition-all" 
          onClick={handleExtract}
          disabled={isExtracting}
        >
          {isExtracting ? (
            <div className="flex items-center gap-2 flex-col absolute inset-0 justify-center bg-primary rounded-full">
               <div className="flex items-center gap-2">
                 <Loader2 className="w-4 h-4 animate-spin" />
                 <span>{steps[Math.min(loadingStep, steps.length - 1)]}</span>
               </div>
            </div>
          ) : (
            <>
              <Play className="w-4 h-4 mr-2 fill-current" />
              Extract & Verify Boundary
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
