/**
 * PrintAdjustmentModal — Phase 4 (THE MOAT)
 *
 * Before generating the PDF, the user sees a full-screen map that shows the
 * exact same satellite view as the main map. They pan / zoom to frame the
 * parcel exactly how they want it to appear in the PDF.
 *
 * On "Confirm & Generate PDF", the current viewport (center_lat, center_lng,
 * zoom) is sent to POST /api/report/{id}/generate-pdf.
 *
 * Matches the old engine's print-adjustment-modal behaviour exactly.
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MapContainer, TileLayer, Polygon, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { X, Download, Loader2, AlertCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useAppContext } from "@/context/AppContext";
import { apiUrl } from "@/lib/api";
import { MapErrorBoundary } from "../map/MapErrorBoundary";

const HYBRID_TILES = {
  url: "https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}",
  subdomains: ["mt0", "mt1", "mt2", "mt3"],
  maxZoom: 24,
  maxNativeZoom: 20,
};

const POLYGON_STYLE = {
  color: "#DC2626",
  fillColor: "#DC2626",
  fillOpacity: 0.12,
  weight: 3,
};

interface PrintAdjustmentModalProps {
  reportId: string;
  mode: "simple" | "expert";
  exportFormat: "pdf" | "png";
  onClose: () => void;
  onDownloaded: () => void;
}

/** Capture map viewport into a ref as the user pans/zooms */
function ViewportCapture({
  viewportRef,
}: {
  viewportRef: React.MutableRefObject<{ lat: number; lng: number; zoom: number }>;
}) {
  const map = useMapEvents({
    moveend: () => {
      const c = map.getCenter();
      viewportRef.current = { lat: c.lat, lng: c.lng, zoom: map.getZoom() };
    },
    zoomend: () => {
      const c = map.getCenter();
      viewportRef.current = { lat: c.lat, lng: c.lng, zoom: map.getZoom() };
    },
  });
  return null;
}

/** Auto-fly to parcel on first render */
function FlyToParcel({ coords }: { coords: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    const validCoords = coords.filter(c => c && !isNaN(c[0]) && !isNaN(c[1]));
    if (!validCoords.length) return;
    const bounds = L.latLngBounds(validCoords.map(([lat, lng]) => L.latLng(lat, lng)));
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 18 });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function PrintAdjustmentModal({
  reportId,
  mode,
  exportFormat,
  onClose,
  onDownloaded,
}: PrintAdjustmentModalProps) {
  const { parcelCoords, mapViewport, tileStyle } = useAppContext();
  const { toast } = useToast();
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  // Start from current main-map viewport; update as user pans
  const viewportRef = useRef({
    lat: mapViewport?.lat ?? 9.082,
    lng: mapViewport?.lng ?? 8.6753,
    zoom: mapViewport?.zoom ?? 15,
  });

  const initialLat = Number(viewportRef.current.lat);
  const initialLng = Number(viewportRef.current.lng);
  const center: [number, number] = [
    !isNaN(initialLat) && initialLat !== 0 ? initialLat : 9.082,
    !isNaN(initialLng) && initialLng !== 0 ? initialLng : 8.6753,
  ];

  const validParcelCoords = (parcelCoords || [])
    .map((c: any) => [Number(c[0]), Number(c[1])] as [number, number])
    .filter((c: any) => c && c.length >= 2 && !isNaN(c[0]) && !isNaN(c[1]));

  const handleGenerate = async () => {
    setIsGenerating(true);
    setGenError(null);
    const vp = viewportRef.current;
    try {
      const endpoint = exportFormat === "png"
        ? apiUrl(`/api/report/${reportId}/generate-card`)
        : apiUrl(`/api/report/${reportId}/generate-pdf?mode=${mode}&include_elevation_profile=${mode === "expert"}`);

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          map_viewport: {
            lat: vp.lat,
            lng: vp.lng,
            zoom: vp.zoom,
          },
          tile_style: tileStyle,
        }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const ext = exportFormat === "png" ? "png" : "pdf";
        const prefix = exportFormat === "png" ? "LandIQ_Card" : `LandIQ_${mode}`;
        a.download = `${prefix}_${reportId.slice(0, 8)}.${ext}`;
        if (typeof a.download === "undefined") {
          window.open(url, "_blank");
        } else {
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }
        setTimeout(() => window.URL.revokeObjectURL(url), 10000);
        onDownloaded();
        onClose();
      } else {
        // Attempt to read the FastAPI error detail
        let detail = `Server error ${res.status}`;
        try {
          const body = await res.json();
          detail = body?.detail || detail;
        } catch { /* response was not JSON */ }
        setGenError(detail);
        toast({
          title: `${exportFormat.toUpperCase()} Export Failed`,
          description: detail,
          variant: "destructive",
        });
      }
    } catch (e: any) {
      const msg = e?.message || "Network error — check server connection.";
      setGenError(msg);
      toast({
        title: `${exportFormat.toUpperCase()} Export Failed`,
        description: msg,
        variant: "destructive",
      });
      console.error(`${exportFormat.toUpperCase()} generation failed:`, e);
    } finally {
      setIsGenerating(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex flex-col bg-background animate-in slide-in-from-bottom-4 duration-300"
      style={{ background: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)" }}
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-5 pt-[calc(env(safe-area-inset-top,0px)+16px)] lg:pt-4 pb-4 bg-card border-b border-border flex-shrink-0">
        <div>
          <h3 className="font-bold text-foreground text-base">
            Adjust Map for {exportFormat === "png" ? "PNG Export" : "PDF Export"}
          </h3>
          <p className="text-muted-foreground text-xs mt-0.5">
            Pan and zoom to frame the parcel exactly as you want it in the {exportFormat === "png" ? "PNG card" : "PDF"}, then confirm.
          </p>
        </div>
        <button
          onClick={onClose}
          className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-muted transition-colors text-muted-foreground"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Adjustment Map ── */}
      <div className="flex-1 relative">
        <MapErrorBoundary>
          <MapContainer
            center={center}
            zoom={viewportRef.current.zoom}
            zoomControl
            className="w-full h-full"
            style={{ height: "100%", width: "100%" }}
          >
            {tileStyle === "esri_hybrid" ? (
              <>
                <TileLayer
                  key="esri_base_modal"
                  url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                  maxZoom={19}
                  attribution="Tiles &copy; Esri"
                />
                <TileLayer
                  key="esri_overlay_modal"
                  url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
                  maxZoom={19}
                />
              </>
            ) : tileStyle === "osm" ? (
              <TileLayer
                key="osm_modal"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                subdomains={["a", "b", "c"]}
                maxZoom={19}
                attribution="&copy; OpenStreetMap contributors"
              />
            ) : (
              <TileLayer
                key="google_modal"
                url={HYBRID_TILES.url}
                subdomains={HYBRID_TILES.subdomains as string[]}
                maxZoom={HYBRID_TILES.maxZoom}
                maxNativeZoom={HYBRID_TILES.maxNativeZoom}
                attribution="Map data &copy; Google Hybrid"
              />
            )}
            <ViewportCapture viewportRef={viewportRef} />
            {validParcelCoords.length > 0 && (
              <>
                <FlyToParcel coords={validParcelCoords} />
                <Polygon positions={validParcelCoords} pathOptions={POLYGON_STYLE} />
              </>
            )}
          </MapContainer>
        </MapErrorBoundary>

        {/* Overlay hint */}
        <div
          className="absolute bottom-6 left-1/2 -translate-x-1/2 z-[1000] px-5 py-2.5 rounded-full text-xs font-medium text-white pointer-events-none whitespace-nowrap shadow-lg"
          style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(6px)" }}
        >
          Pan & zoom to frame → confirm below
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="flex items-center justify-end gap-3 px-5 pt-4 pb-[calc(env(safe-area-inset-bottom,0px)+16px)] lg:pb-4 bg-card border-t border-border flex-shrink-0">
        <button
          onClick={onClose}
          className="flex-1 lg:flex-none px-5 py-3 lg:py-2.5 rounded-full border border-border text-sm font-semibold text-foreground hover:bg-muted transition-all active:scale-[0.98]"
        >
          Cancel
        </button>
        {genError && (
          <div className="flex-1 flex items-center gap-2 text-xs text-destructive bg-destructive/10 rounded-xl px-3 py-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span className="line-clamp-2">{genError}</span>
          </div>
        )}
        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className="flex-[2] lg:flex-none px-6 py-3 lg:py-2.5 rounded-full bg-primary text-primary-foreground text-sm font-bold flex items-center justify-center gap-2 hover:bg-primary/90 transition-all shadow-md active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isGenerating
            ? <><Loader2 className="w-4 h-4 animate-spin" /><span>Generating…</span></>
            : <><Download className="w-4 h-4" /><span className="hidden sm:inline">Confirm &amp; Generate {exportFormat === "png" ? "PNG" : "PDF"}</span><span className="sm:hidden">Generate</span></>
          }
        </button>
      </div>
    </div>,
    document.body
  );
}
