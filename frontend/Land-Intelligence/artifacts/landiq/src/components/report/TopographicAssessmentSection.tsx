import { useState, useEffect } from "react";
import { apiUrl } from "@/lib/api";
import { MapContainer, TileLayer, Polygon, Polyline, Tooltip } from "react-leaflet";
import { Mountain, Loader2, AlertCircle } from "lucide-react";
import L from "leaflet";
import { MapErrorBoundary } from "../map/MapErrorBoundary";

interface Point {
  x: number;
  y: number;
}

interface Segment {
  p1: Point;
  p2: Point;
}

// ── Marching Squares algorithm for client-side contour generation ──
function marchingSquares(grid: number[][], level: number): Segment[] {
  const segments: Segment[] = [];
  const R = grid.length;
  if (R === 0) return [];
  const C = grid[0].length;

  for (let r = 0; r < R - 1; r++) {
    for (let c = 0; c < C - 1; c++) {
      const v0 = grid[r][c];         // Top-Left
      const v1 = grid[r][c + 1];     // Top-Right
      const v2 = grid[r + 1][c + 1]; // Bottom-Right
      const v3 = grid[r + 1][c];     // Bottom-Left

      const b0 = v0 >= level ? 8 : 0;
      const b1 = v1 >= level ? 4 : 0;
      const b2 = v2 >= level ? 2 : 0;
      const b3 = v3 >= level ? 1 : 0;

      const cellCase = b0 | b1 | b2 | b3;
      if (cellCase === 0 || cellCase === 15) continue;

      const interpolate = (valA: number, valB: number): number => {
        if (Math.abs(valA - valB) < 1e-6) return 0.5;
        return (level - valA) / (valB - valA);
      };

      const top = { x: c + interpolate(v0, v1), y: r };
      const right = { x: c + 1, y: r + interpolate(v1, v2) };
      const bottom = { x: c + interpolate(v3, v2), y: r + 1 };
      const left = { x: c, y: r + interpolate(v0, v3) };

      switch (cellCase) {
        case 1:
          segments.push({ p1: left, p2: bottom });
          break;
        case 2:
          segments.push({ p1: bottom, p2: right });
          break;
        case 3:
          segments.push({ p1: left, p2: right });
          break;
        case 4:
          segments.push({ p1: top, p2: right });
          break;
        case 5:
          segments.push({ p1: left, p2: top });
          segments.push({ p1: bottom, p2: right });
          break;
        case 6:
          segments.push({ p1: top, p2: bottom });
          break;
        case 7:
          segments.push({ p1: left, p2: top });
          break;
        case 8:
          segments.push({ p1: left, p2: top });
          break;
        case 9:
          segments.push({ p1: top, p2: bottom });
          break;
        case 10:
          segments.push({ p1: left, p2: bottom });
          segments.push({ p1: top, p2: right });
          break;
        case 11:
          segments.push({ p1: top, p2: right });
          break;
        case 12:
          segments.push({ p1: left, p2: right });
          break;
        case 13:
          segments.push({ p1: bottom, p2: right });
          break;
        case 14:
          segments.push({ p1: left, p2: bottom });
          break;
      }
    }
  }

  return segments;
}

const gridToLatLng = (p: Point, R: number, C: number, bounds: number[][]): [number, number] | null => {
  const minLat = bounds[0][0];
  const minLng = bounds[0][1];
  const maxLat = bounds[1][0];
  const maxLng = bounds[1][1];

  // Guard: avoid division by zero on degenerate grids
  if (C <= 1 || R <= 1) return null;
  if (!isFinite(minLat) || !isFinite(minLng) || !isFinite(maxLat) || !isFinite(maxLng)) return null;

  const lng = minLng + (p.x / (C - 1)) * (maxLng - minLng);
  const lat = maxLat - (p.y / (R - 1)) * (maxLat - minLat);
  if (!isFinite(lat) || !isFinite(lng)) return null;
  return [lat, lng];
};

interface TopographicAssessmentSectionProps {
  reportId: string;
  parcelCoords: [number, number][];
}

export function TopographicAssessmentSection({ reportId, parcelCoords }: TopographicAssessmentSectionProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) return;
    setLoading(true);
    setError(null);
    fetch(apiUrl(`/api/report/${reportId}/gee-elevation`))
      .then((res) => {
        if (!res.ok) {
          throw new Error("Failed to load GEE elevation data.");
        }
        return res.json();
      })
      .then((resData) => {
        if (resData.elevation_available === false) {
          setError(resData.message || "Topographic dataset is currently unavailable.");
        } else {
          setData(resData);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "An error occurred fetching GEE data.");
        setLoading(false);
      });
  }, [reportId]);

  if (loading) {
    return (
      <div className="bg-card border border-border/60 rounded-2xl p-6 flex flex-col items-center justify-center text-muted-foreground gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
        <p className="text-xs font-semibold">Generating Topographic Contour Grid…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-card border border-border/60 rounded-2xl p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-amber-500">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <h4 className="text-sm font-bold">Topographic Assessment Unavailable</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Topography Data Unavailable: All upstream satellite providers (NASA, SRTM, JAXA) failed to respond. The report has proceeded without 3D elevation profiling.
        </p>
      </div>
    );
  }

  const { grid, bounds, scale_m, interval_m, min_elevation, max_elevation, dimensions } = data;
  const R = dimensions ? dimensions[0] : 0;
  const C = dimensions ? dimensions[1] : 0;

  // Fallback to parcelCoords if bounds is missing (e.g. old cache)
  const validBounds = bounds || parcelCoords;

  if (!validBounds || validBounds.length === 0 || !grid || R === 0 || C === 0) {
    return (
      <div className="bg-card border border-border/60 rounded-2xl p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-amber-500">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <h4 className="text-sm font-bold">Topographic Assessment Unavailable</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          The topographic dataset for this area is incomplete or invalid.
        </p>
      </div>
    );
  }

  // Fit map boundaries
  const mapBounds = L.latLngBounds(validBounds);

  // Compute contour levels
  const levels: number[] = [];
  const start = Math.floor(min_elevation / interval_m) * interval_m;
  const end = Math.ceil(max_elevation / interval_m) * interval_m;
  for (let l = start; l <= end; l += interval_m) {
    levels.push(l);
  }

  return (
    <div className="bg-card border border-border/60 rounded-2xl overflow-hidden flex flex-col">
      {/* Label header */}
      <div className="p-4 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Mountain className="w-4 h-4 text-[#0058BD]" />
          <span className="text-xs font-bold text-foreground uppercase tracking-wider">Expert Topographic Assessment</span>
        </div>
        <span className="text-[9px] font-mono font-bold tracking-widest text-[#0058BD] bg-[#0058BD]/10 px-2 py-0.5 rounded-full">
          30M ELEVATION MODEL
        </span>
      </div>

      {/* Map view container */}
      <div className="h-[220px] w-full relative z-10 border-b border-border/50">
        <MapErrorBoundary>
          <MapContainer
            bounds={mapBounds}
            zoomControl={false}
            attributionControl={false}
            className="w-full h-full"
          >
          {/* Google Satellite Hybrid layer */}
          <TileLayer
            url="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"
            maxZoom={20}
          />

          {/* Rendering Contour vector lines via client-side Marching Squares */}
          {levels.map((lvl) => {
            const segments = marchingSquares(grid, lvl);
            if (segments.length === 0) return null;

            const isIndex = lvl % (interval_m * 5) === 0;
            const linePositions = segments
              .map((seg) => {
                const p1 = gridToLatLng(seg.p1, R, C, bounds);
                const p2 = gridToLatLng(seg.p2, R, C, bounds);
                if (!p1 || !p2) return null;
                return [p1, p2] as [number, number][];
              })
              .filter((s): s is [number, number][] => s !== null);

            if (linePositions.length === 0) return null;

            // Render MultiPolyline for performance
            return (
              <Polyline
                key={lvl}
                positions={linePositions}
                pathOptions={{
                  color: "#ffffff",
                  weight: isIndex ? 2.0 : 0.8,
                  opacity: isIndex ? 0.6 : 0.35,
                }}
              >
                {isIndex && segments.length > 5 && (
                  <Tooltip
                    permanent
                    direction="center"
                    className="bg-transparent border-0 text-[8px] text-white/90 font-mono font-bold shadow-none p-0 select-none pointer-events-none"
                  >
                    {lvl}m
                  </Tooltip>
                )}
              </Polyline>
            );
          })}

          {/* Blue parcel boundary */}
          {parcelCoords && parcelCoords.length > 0 && (
            <Polygon
              positions={parcelCoords}
              pathOptions={{
                color: "#0058BD",
                fillColor: "#0058BD",
                fillOpacity: 0.15,
                weight: 3.0,
              }}
            />
          )}
        </MapContainer>
      </MapErrorBoundary>
      </div>

      {/* Detail notes card */}
      <div className="p-4 bg-muted/20 dark:bg-muted/10 space-y-2 text-xs leading-relaxed text-muted-foreground">
        <p className="font-semibold text-foreground">Topographic Elevation Context</p>
        <p>
          Calculated at a resampled grid resolution of <strong className="text-foreground">{scale_m}m</strong> using satellite elevation modeling.
          The vertical height ranges from <strong className="text-foreground">{min_elevation}m</strong> to <strong className="text-foreground">{max_elevation}m</strong> above mean sea level,
          with standard contour intervals of <strong className="text-foreground">{interval_m}m</strong>.
        </p>
        <p className="text-[10px] text-muted-foreground italic">
          Note: This contour model is an engineering approximation processed directly from NASADEM satellite data and is intended for preliminary site planning only.
        </p>
      </div>
    </div>
  );
}
