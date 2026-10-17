import React, { useState, useEffect, useRef } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Plus, Trash2, Info, X } from "lucide-react";
import { useAppContext } from "@/context/AppContext";
import { apiUrl } from "@/lib/api";

export interface COGOPayload {
  input_mode: string;
  starting_point: {
    easting: number;
    northing: number;
    crs: string;
    confidence: string;
  };
  cogo_vectors: Array<{
    station_id: string;
    easting_raw: number;
    northing_raw: number;
    bearing: string;
    distance: number;
  }>;
}

interface Props {
  onPayloadChange: (payload: COGOPayload | null) => void;
}

export function CogoTraverseGrid({ onPayloadChange }: Props) {
  const { formData, setFormData, setCogoDraftCoords, setCogoClosureGap } = useAppContext();
  const { cogoStartEasting: startEasting, cogoStartNorthing: startNorthing, cogoStartCrs: startCrs, cogoRows: rows } = formData;
  
  const setStartEasting = (val: string) => setFormData(prev => ({ ...prev, cogoStartEasting: val }));
  const setStartNorthing = (val: string) => setFormData(prev => ({ ...prev, cogoStartNorthing: val }));
  const setStartCrs = (val: string) => setFormData(prev => ({ ...prev, cogoStartCrs: val }));
  const setRows = (newRows: any) => setFormData(prev => ({ ...prev, cogoRows: newRows }));

  const [closureInfo, setClosureInfo] = useState<{ errorM: number; colorClass: string } | null>(null);
  const [bearingInfoOpen, setBearingInfoOpen] = useState(false);
  const [idInfoOpen, setIdInfoOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  const parseBearing = (bStr: string) => {
    if (!bStr) return null;
    bStr = bStr.toUpperCase().trim();
    const quadMatch = bStr.match(/^([NS])[\-\s]*(\d{1,3})[°\-\s]*(\d{0,2})['\-\s]*(\d{0,2})["\-\s]*([EW])$/);
    
    if (quadMatch) {
      const ns = quadMatch[1];
      const deg = parseFloat(quadMatch[2]) || 0;
      const min = parseFloat(quadMatch[3]) || 0;
      const sec = parseFloat(quadMatch[4]) || 0;
      const angle = deg + (min / 60) + (sec / 3600);
      const ew = quadMatch[5];
      
      if (ns === 'N' && ew === 'E') return angle;
      if (ns === 'S' && ew === 'E') return 180 - angle;
      if (ns === 'S' && ew === 'W') return 180 + angle;
      if (ns === 'N' && ew === 'W') return 360 - angle;
    } else {
      const parts = bStr.split(/[°'"\-\s]+/).filter(Boolean);
      if (parts.length > 0) {
        const deg = parseFloat(parts[0]) || 0;
        const min = parseFloat(parts[1]) || 0;
        const sec = parseFloat(parts[2]) || 0;
        return (deg + (min / 60) + (sec / 3600)) % 360;
      }
    }
    return null;
  };

  // ── Local closure indicator (instant, no network) ──────────────────────────
  useEffect(() => {
    const startE = parseFloat(startEasting);
    const startN = parseFloat(startNorthing);
    
    if (isNaN(startE) || isNaN(startN)) {
      setClosureInfo(null);
      onPayloadChange(null);
      return;
    }
    
    let currE = startE;
    let currN = startN;
    let validRows = 0;
    
    const validVectors = [];
    
    for (const row of rows) {
      const dist = parseFloat(row.distance);
      const az = parseBearing(row.bearing);
      
      if (az !== null && !isNaN(dist) && dist > 0) {
        const azRad = az * (Math.PI / 180);
        currE += dist * Math.sin(azRad);
        currN += dist * Math.cos(azRad);
        validRows++;
        
        validVectors.push({
          station_id: row.id,
          easting_raw: 0,
          northing_raw: 0,
          bearing: row.bearing,
          distance: dist
        });
      }
    }
    
    if (validRows > 2) {
      const errE = currE - startE;
      const errN = currN - startN;
      const errM = Math.sqrt(errE * errE + errN * errN);
      
      let colorClass = "text-danger";
      if (errM <= 0.10) colorClass = "text-green-500 font-bold";
      else if (errM <= 0.50) colorClass = "text-emerald-500 font-bold";
      else if (errM <= 2.00) colorClass = "text-amber-500 font-bold";
      else colorClass = "text-red-500 font-bold";
      
      setClosureInfo({ errorM: errM, colorClass });
    } else {
      setClosureInfo(null);
    }
    
    if (validVectors.length >= 3) {
      onPayloadChange({
        input_mode: "cogo_traverse",
        starting_point: {
          easting: startE,
          northing: startN,
          crs: startCrs,
          confidence: "confirmed"
        },
        cogo_vectors: validVectors
      });
    } else {
      onPayloadChange(null);
    }
  }, [startEasting, startNorthing, startCrs, rows]);

  // ── Debounced draft API call for live map plotter ──────────────────────────
  useEffect(() => {
    const startE = parseFloat(startEasting);
    const startN = parseFloat(startNorthing);
    const validRows = rows.filter(r => r.bearing.trim() && parseFloat(r.distance) > 0);

    // Need at least 1 valid row and a valid starting point
    if (isNaN(startE) || isNaN(startN) || validRows.length < 1) {
      setCogoDraftCoords([]);
      setCogoClosureGap(null);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(apiUrl("/api/cogo/draft"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            start_easting: startE,
            start_northing: startN,
            crs: startCrs,
            rows: validRows.map(r => ({
              station_id: r.id,
              bearing: r.bearing,
              distance: parseFloat(r.distance),
            })),
          }),
        });
        if (!res.ok) return;
        const data = await res.json();
        setCogoDraftCoords(data.wgs_coords || []);
        setCogoClosureGap({ errorMeters: data.closure_error_m, isClosed: data.is_closed });
      } catch {
        // Silently fail — draft is optional visual feedback
      }
    }, 300);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [startEasting, startNorthing, startCrs, rows]);

  const rowRefs = useRef<(HTMLInputElement | null)[]>([]);

  const addRow = () => {
    const newIdx = rows.length;
    setRows([...rows, { id: `S${rows.length + 1}-S${rows.length + 2}`, bearing: "", distance: "" }]);
    setTimeout(() => {
      if (rowRefs.current[newIdx]) {
        rowRefs.current[newIdx]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        rowRefs.current[newIdx]?.focus();
      }
    }, 50);
  };

  const updateRow = (index: number, field: keyof typeof rows[0], value: string) => {
    const newRows = [...rows];
    newRows[index][field] = value;
    setRows(newRows);
  };

  const removeRow = (index: number) => {
    const newRows = [...rows];
    newRows.splice(index, 1);
    setRows(newRows);
  };

  return (
    <div className="space-y-5 border rounded-xl p-4 bg-background shadow-sm border-border">
      <div className="space-y-2 border-b border-border/50 pb-4">
        <Label className="text-xs font-semibold text-foreground">Starting Coordinate</Label>
        <div className="flex gap-2">
          <Input 
            placeholder="Easting" 
            value={startEasting}
            onChange={e => setStartEasting(e.target.value)}
            className="flex-1 min-w-0 text-sm h-11 rounded-xl placeholder:font-sans bg-background [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            type="number"
          />
          <Input 
            placeholder="Northing" 
            value={startNorthing}
            onChange={e => setStartNorthing(e.target.value)}
            className="flex-1 min-w-0 text-sm h-11 rounded-xl placeholder:font-sans bg-background [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            type="number"
          />
          <Select value={startCrs} onValueChange={setStartCrs}>
            <SelectTrigger className="w-[80px] flex-shrink-0 h-11 rounded-xl text-sm px-3 bg-background shadow-sm border-input">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="EPSG:32631">31N</SelectItem>
                <SelectItem value="EPSG:32632">32N</SelectItem>
                <SelectItem value="EPSG:32633">33N</SelectItem>
              </SelectContent>
            </Select>
        </div>
      </div>

      <div className="flex justify-center my-3">
        <div className="bg-background border border-border/50 rounded-full px-3 py-1.5 flex items-center gap-2 shadow-sm">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            Live Closure
          </span>
          <span className="w-px h-3 bg-border"></span>
          {closureInfo ? (
            <span className={`text-[11px] font-bold ${closureInfo.colorClass}`}>{closureInfo.errorM.toFixed(2)}m</span>
          ) : (
            <span className="text-[11px] font-bold text-muted-foreground">--</span>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="grid grid-cols-[60px_1fr_90px_36px] gap-2">
          <div className="flex items-center justify-center gap-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider text-center">
            ID
            <button
              type="button"
              onClick={() => setIdInfoOpen(o => !o)}
              className="text-muted-foreground/70 active:text-primary transition-colors"
              aria-label="ID format help"
            >
              {idInfoOpen ? <X className="w-3 h-3" /> : <Info className="w-3 h-3" />}
            </button>
          </div>
          <div className="flex items-center gap-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider pl-1">
            Bearing
            <button
              type="button"
              onClick={() => setBearingInfoOpen(o => !o)}
              className="ml-0.5 text-muted-foreground/70 active:text-primary transition-colors"
              aria-label="Bearing format help"
            >
              {bearingInfoOpen ? <X className="w-3 h-3" /> : <Info className="w-3 h-3" />}
            </button>
          </div>
          <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider pl-2">Dist(m)</div>
          <div></div>
        </div>

        {/* Tap-to-toggle inline ID format guide */}
        {idInfoOpen && (
          <div className="rounded-lg bg-muted/60 border border-border/50 px-3 py-2 text-xs space-y-1 text-foreground/80">
            <p>To draw your plot, the last line must connect to your starting point (e.g S7-S1)</p>
          </div>
        )}

        {/* Tap-to-toggle inline bearing format guide — works on mobile */}
        {bearingInfoOpen && (
          <div className="rounded-lg bg-muted/60 border border-border/50 px-3 py-2 text-xs space-y-1 text-foreground/80">
            <p className="font-semibold text-foreground mb-1">Supported Bearing Formats</p>
            <p><span className="font-medium">Decimal:</span> 135.5</p>
            <p><span className="font-medium">Hyphens:</span> 135-30-15 or S45-30-15E</p>
            <p><span className="font-medium">Symbols:</span> 135°30&#39;15&quot; or S45°30&#39;15&quot;E</p>
            <p><span className="font-medium">Spaces:</span> 135 30 15 or S 45 30 15 E</p>
          </div>
        )}
        
        {/* Cap visible rows at ~4 — scrollable internally so Extract button stays reachable */}
        <div className="max-h-[180px] overflow-y-auto overscroll-contain space-y-2 pr-1 pb-1">
          {rows.map((row, idx) => (
            <div key={idx} className="grid grid-cols-[60px_1fr_90px_36px] gap-2 items-center">
              <Input 
                ref={el => { rowRefs.current[idx] = el; }}
                value={row.id} 
                onChange={(e) => updateRow(idx, "id", e.target.value)}
                className="w-full text-sm h-11 rounded-xl px-1 text-center bg-background relative focus:z-10"
              />
              <Input 
                value={row.bearing} 
                onChange={(e) => updateRow(idx, "bearing", e.target.value)}
                placeholder="e.g. 135-30-15"
                className="w-full min-w-0 text-sm h-11 rounded-xl pl-3 pr-2 bg-background relative focus:z-10"
              />
              <Input 
                value={row.distance} 
                onChange={(e) => updateRow(idx, "distance", e.target.value)}
                placeholder="Length"
                type="number"
                className="w-full text-sm h-11 rounded-xl pl-3 pr-2 bg-background [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none relative focus:z-10"
              />
              <Button 
                variant="ghost" 
                size="icon" 
                className="w-9 h-11 rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                onClick={() => removeRow(idx)}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-between items-center pt-2">
        <Button 
          variant="outline" 
          size="sm" 
          className="h-9 text-sm font-medium"
          onClick={addRow}
        >
          <Plus className="w-4 h-4 mr-1.5" /> Add Leg
        </Button>
      </div>
    </div>
  );
}
