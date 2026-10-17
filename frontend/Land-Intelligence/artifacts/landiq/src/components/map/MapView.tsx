import React, { useState, useMemo, useEffect, useRef } from "react";

import { MapContainer, TileLayer, Polygon, Polyline, CircleMarker, Tooltip, Marker, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { useSafeFitBounds } from "@/hooks/useSafeFitBounds";
import { useLocation } from "wouter";
import "leaflet/dist/leaflet.css";
import { useAppContext, TileStyle } from "@/context/AppContext";
import { Plus, Minus, Layers } from "lucide-react";
import { MapErrorBoundary } from "./MapErrorBoundary";
import { PremiumDraftOverlay } from "@/components/analyse/PremiumDraftOverlay";

// ─── Composite Lot Layer ───────────────────────────────────────────────────────
// Renders master boundary + subdivision grid for PlanType.TYPE_B plans.
function CompositeLotLayer({
  lots,
  masterBoundary,
  selectedLotId,
  setSelectedLotId,
}: {
  lots: Array<{ lot_id: string; coordinates: [number, number][]; centroid?: [number, number] | null }>;
  masterBoundary: [number, number][];
  selectedLotId: string | null;
  setSelectedLotId: (id: string | null) => void;
}) {
  const map = useMap();

  return (
    <>
      {/* Master boundary — brand red perimeter, no fill */}
      {masterBoundary.length >= 3 && (
        <Polygon
          positions={masterBoundary}
          pathOptions={{ color: "#DC2626", weight: 3.5, fill: false, opacity: 0.9 }}
        />
      )}

      {/* Subdivision grid + centroid labels */}
      {lots.map((lot) => {
        const isSelected = selectedLotId === lot.lot_id;
        const validCoords = (lot.coordinates || [])
          .map((c) => [Number(c[0]), Number(c[1])] as [number, number])
          .filter((c) => !isNaN(c[0]) && !isNaN(c[1]));
        if (validCoords.length < 3) return null;

        // Validate centroid before using it
        const centroid = lot.centroid
          ? (() => {
              const lat = Number(lot.centroid[0]);
              const lng = Number(lot.centroid[1]);
              return !isNaN(lat) && !isNaN(lng) ? [lat, lng] as [number, number] : null;
            })()
          : null;

        return (
          <React.Fragment key={lot.lot_id}>
            {/* Lot polygon */}
            <Polygon
              positions={validCoords}
              pathOptions={isSelected
                // Selected: neon electric teal — high contrast active state
                ? { color: "#00FFCC", weight: 3, fillColor: "#00FFCC", fillOpacity: 0.22, opacity: 1 }
                // Unselected: black grid lines — clear delineation without competing with selection
                : { color: "#000000", weight: 1.8, fillColor: "#000000", fillOpacity: 0.03, opacity: 0.50 }
              }
              eventHandlers={{
                click: () => {
                  setSelectedLotId(isSelected ? null : lot.lot_id);
                  if (!isSelected && centroid) {
                    try { map.flyTo(centroid, 18, { animate: true, duration: 0.8 }); } catch { /* noop */ }
                  }
                },
              }}
            />
            {/* Lot ID label — DivIcon at centroid guarantees perfect center alignment */}
            {centroid && (
              <Marker
                position={centroid}
                icon={L.divIcon({
                  html: `<div style="transform: translate(-50%, -50%); display: inline-block; white-space: nowrap;">
                           <span style="font-size: 14px; font-family: 'Inter', sans-serif; font-weight: 700; color: #ffffff; text-shadow: 0 1px 4px rgba(0,0,0,0.9); letter-spacing: 0.02em;">
                             ${lot.lot_id}
                           </span>
                         </div>`,
                  className: '', // Strips default Leaflet backgrounds/borders
                  iconSize: [0, 0],
                  iconAnchor: [0, 0] 
                })}
              />
            )}
          </React.Fragment>
        );
      })}
    </>
  );
}



// ─── Tile definitions ──────────────────────────────────────────────────────────
// Single-TileLayer configs (satellite + osm)
const SINGLE_TILES: Record<"satellite" | "osm", { url: string; subdomains: string[]; maxZoom: number; maxNativeZoom: number; attribution: string }> = {
  satellite: {
    url: "https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}",
    subdomains: ["mt0", "mt1", "mt2", "mt3"],
    maxZoom: 24,
    maxNativeZoom: 20,
    attribution: "Map data &copy; Google Hybrid",
  },
  osm: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    subdomains: ["a", "b", "c"],
    maxZoom: 19,
    maxNativeZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
};

// Esri Hybrid — dual-stacked layers (base imagery + label overlay)
const ESRI_TILES = {
  baseUrl: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  overlayUrl: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
  maxZoom: 19,
  attribution: "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
};

// Nigeria centroid — map starts here
const NIGERIA_CENTER: [number, number] = [9.082, 8.6753];
const NIGERIA_ZOOM = 7;

// Polygon style
const POLYGON_STYLE = {
  color: "#DC2626",
  fillColor: "#DC2626",
  fillOpacity: 0.12,
  weight: 3,
};

// ─── Active Tile Layer Switcher ───────────────────────────────────────────────
// Uses the imperative Leaflet API (useMap + useEffect) to add/remove tile layers
// whenever tileStyle changes. This is necessary because React-Leaflet's reconciler
// doesn't correctly unmount the old TileLayer when switching between a single layer
// and a dual-layer (Esri Hybrid) Fragment — leaving the old tiles stacked underneath.
function ActiveTileLayer({ tileStyle }: { tileStyle: TileStyle }) {
  const map = useMap();

  useEffect(() => {
    // Collect all current tile layers from the map and remove them
    const toRemove: L.TileLayer[] = [];
    map.eachLayer((layer) => {
      if (layer instanceof L.TileLayer) {
        toRemove.push(layer);
      }
    });
    toRemove.forEach((layer) => map.removeLayer(layer));

    // Add the correct tile layer(s) for the selected style
    if (tileStyle === "esri_hybrid") {
      L.tileLayer(ESRI_TILES.baseUrl, {
        maxZoom: ESRI_TILES.maxZoom,
        attribution: ESRI_TILES.attribution,
      }).addTo(map);
      L.tileLayer(ESRI_TILES.overlayUrl, {
        maxZoom: ESRI_TILES.maxZoom,
      }).addTo(map);
    } else {
      const cfg = SINGLE_TILES[tileStyle];
      L.tileLayer(cfg.url, {
        subdomains: cfg.subdomains,
        maxZoom: cfg.maxZoom,
        maxNativeZoom: cfg.maxNativeZoom,
        attribution: cfg.attribution,
      }).addTo(map);
    }
  }, [map, tileStyle]); // eslint-disable-line react-hooks/exhaustive-deps

  return null;
}

// ─── Main export ──────────────────────────────────────────────────────────────
export function MapView({ onExtract }: { onExtract?: () => void }) {
  const [, setLocation] = useLocation();
  const { analysisState, setMapViewport, parcelCoords, cogoDraftCoords, cogoClosureGap, reportData, selectedLotId, setSelectedLotId, tileStyle, setTileStyle } = useAppContext();
  const hasAnalysis = analysisState === "gate" || analysisState === "complete";
  const isDrafting = cogoDraftCoords.length >= 2;
  const showClosedOverlay = cogoClosureGap?.isClosed && !hasAnalysis;

  // Composite survey data (reads from real reportData in production)
  const isComposite = hasAnalysis && reportData?.parcel_geometry?.is_composite === true;
  const geom = reportData?.parcel_geometry;
  const lots = isComposite && geom ? (geom.lots ?? []) : [];
  const masterBoundary: [number, number][] = (isComposite && geom?.master_boundary ? geom.master_boundary : [])
    .map((c: any) => [Number(c[0]), Number(c[1])] as [number, number]);

  // Sanitize coords
  const validCoords = Array.isArray(parcelCoords)
    ? (parcelCoords as [number, number][])
        .map((c) => [Number(c[0]), Number(c[1])] as [number, number])
        .filter((c) => c && c.length >= 2 && !isNaN(c[0]) && !isNaN(c[1]))
    : [];

  const mapBounds = useMemo(() => {
    return validCoords.length >= 3 ? L.latLngBounds(validCoords) : null;
  }, [JSON.stringify(validCoords)]);

  const handleNextTileLayer = () => {
    setTileStyle((prev) => {
      if (prev === "satellite") return "esri_hybrid";
      if (prev === "esri_hybrid") return "osm";
      return "satellite";
    });
  };

  return (
    <div className="absolute inset-0 z-0">
      <MapErrorBoundary>
        <MapContainer
          center={NIGERIA_CENTER}
          zoom={NIGERIA_ZOOM}
          zoomControl={false}
          className="w-full h-full"
          style={{ height: "100%", width: "100%", minHeight: "400px" }}
        >
          {/* Imperative tile layer switcher — avoids React-Leaflet reconciliation
              issues when switching between single-layer and dual-layer (Esri) configs */}
          <ActiveTileLayer tileStyle={tileStyle} />

          {/* Map event tracker — keeps mapViewport in sync for PDF export */}
          <MapEventsHandler setMapViewport={setMapViewport} />

          {/* Carousel → Map flyTo bridge: listens for landiq:flyto-lot events */}
          <FlyToLotController />

          {/* Fly and zoom tight to parcel when real coords arrive */}
          <SafeBoundsComponent bounds={mapBounds} />

          {/* COGO Draft layer — renders over true location, blur is CSS-only */}
          {isDrafting && !hasAnalysis && (
            <CogoDraftLayer coords={cogoDraftCoords} closureGap={cogoClosureGap} />
          )}

          {/* Composite multi-lot layer — only for TYPE_B plans */}
          {isComposite && (
            <CompositeLotLayer
              lots={lots}
              masterBoundary={masterBoundary}
              selectedLotId={selectedLotId}
              setSelectedLotId={setSelectedLotId}
            />
          )}

          {/* Red polygon boundary — only for single-parcel (non-composite) plans */}
          {hasAnalysis && !isComposite && validCoords.length > 0 && (
            <Polygon
              positions={validCoords}
              pathOptions={POLYGON_STYLE}
              eventHandlers={{ click: () => setLocation('/gate') }}
            />
          )}

          {/* Blur injector + cinematic unblur on extraction */}
          <TileBlurController isDrafting={isDrafting} hasAnalysis={hasAnalysis} parcelBounds={mapBounds} />

          {/* Controls rendered inside MapContainer so useMap() works */}
          <MapControls
            tileStyle={tileStyle}
            onToggleLayer={handleNextTileLayer}
          />
        </MapContainer>
      </MapErrorBoundary>

      {/* Engineering grid overlay — only during draft mode */}
      {isDrafting && !hasAnalysis && <DraftingGridOverlay />}

      {/* Closed geometry premium overlay */}
      {showClosedOverlay && onExtract && (
        <PremiumDraftOverlay
          closureErrorM={cogoClosureGap!.errorMeters}
          onExtract={onExtract}
        />
      )}

      {/* Empty state overlay */}
      {!hasAnalysis && validCoords.length === 0 && !isDrafting && (
        <div
          className="absolute inset-0 pointer-events-none flex items-end justify-center z-[400] px-6"
          style={{ paddingBottom: "calc(72px + 96px)" }}
        >
          <div className="bg-white/92 dark:bg-[#1E2128]/92 backdrop-blur-md px-5 py-4 rounded-2xl shadow-lg border border-border/60 max-w-[280px] w-full text-center pointer-events-auto">
            <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-2.5">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 21.5C12 21.5 20.5 15.5 20.5 9.5C20.5 4.80558 16.6944 1 12 1C7.30558 1 3.5 4.80558 3.5 9.5C3.5 15.5 12 21.5 12 21.5Z"
                  stroke="#DC2626"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M12 12.5C13.6569 12.5 15 11.1569 15 9.5C15 7.84315 13.6569 6.5 12 6.5C10.3431 6.5 9 7.84315 9 9.5C9 11.1569 10.3431 12.5 12 12.5Z"
                  stroke="#DC2626"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <h3 className="font-semibold text-sm text-foreground mb-0.5">
              Spatial Analysis Ready
            </h3>
            <p className="text-muted-foreground text-xs">
              Upload a survey or paste coordinates to begin
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Tile Blur Controller ─────────────────────────────────────────────────────
// Injects blur into Leaflet's tile pane directly and smoothly unblurs on extraction.
function TileBlurController({
  isDrafting,
  hasAnalysis,
  parcelBounds,
}: {
  isDrafting: boolean;
  hasAnalysis: boolean;
  parcelBounds: L.LatLngBounds | null;
}) {
  const map = useMap();
  const prevHasAnalysis = useRef(false);

  useEffect(() => {
    const tilePane = map.getPanes().tilePane as HTMLElement | null;
    if (!tilePane) return;

    if (isDrafting && !hasAnalysis) {
      // No blur as requested by user
      tilePane.style.transition = "filter 0.6s ease";
      tilePane.style.filter = "blur(0px) brightness(1)";
    } else if (hasAnalysis) {
      // Cinematic unblur when extraction completes
      tilePane.style.transition = "filter 1.1s ease";
      tilePane.style.filter = "blur(0px) brightness(1)";

      // Fly to verified parcel bounds after a short delay to let state settle
      if (!prevHasAnalysis.current && parcelBounds) {
        setTimeout(() => {
          try {
            map.flyToBounds(parcelBounds, { padding: [32, 32], maxZoom: 17, duration: 1.4 });
          } catch { /* noop */ }
        }, 400);
      }
    } else {
      // No draft, no analysis — clear any blur
      tilePane.style.transition = "filter 0.4s ease";
      tilePane.style.filter = "blur(0px) brightness(1)";
    }

    prevHasAnalysis.current = hasAnalysis;
  }, [isDrafting, hasAnalysis, parcelBounds]);

  return null;
}

// ─── Engineering Grid Overlay ─────────────────────────────────────────────────
// A crisp SVG-based micro-grid overlaid on the blurred map during drafting.
// Communicates "Drafting Workspace" intentionality — not a crash.
function DraftingGridOverlay() {
  return (
    <div
      className="absolute inset-0 pointer-events-none z-[5]"
      aria-hidden="true"
      style={{
        backgroundImage: `
          linear-gradient(rgba(6, 182, 212, 0.06) 1px, transparent 1px),
          linear-gradient(90deg, rgba(6, 182, 212, 0.06) 1px, transparent 1px),
          linear-gradient(rgba(6, 182, 212, 0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(6, 182, 212, 0.03) 1px, transparent 1px)
        `,
        backgroundSize: "64px 64px, 64px 64px, 16px 16px, 16px 16px",
        backgroundPosition: "-1px -1px, -1px -1px, -1px -1px, -1px -1px",
      }}
    >
      {/* Draft mode badge (Hidden per user request) */}
      <div className="hidden absolute top-4 left-1/2 -translate-x-1/2 z-10">
        <div className="flex items-center gap-2 bg-[#0f172a]/80 backdrop-blur-sm border border-cyan-500/30 rounded-full px-3.5 py-1.5 shadow-lg">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-[11px] font-semibold text-cyan-300 tracking-wide uppercase">
            Drafting Workspace — Location Locked
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Map Controls (Layer toggle + Zoom) ───────────────────────────────────────
function MapControls({
  tileStyle,
  onToggleLayer,
}: {
  tileStyle: TileStyle;
  onToggleLayer: () => void;
}) {
  const map = useMap();
  const btnBase =
    "w-9 h-9 rounded-full shadow-md border flex items-center justify-center transition-all duration-150 text-sm font-bold";
  const btnInactive =
    "bg-white/95 dark:bg-[#1A1D24]/95 border-border text-foreground hover:bg-muted dark:hover:bg-muted/40";

  const nextLabel = tileStyle === "satellite" ? "Esri Hybrid" : tileStyle === "esri_hybrid" ? "OSM Vector" : "Google Hybrid";

  return (
    <div
      className="absolute right-3 z-[500] flex flex-col gap-1.5"
      style={{ top: 80, bottom: 80 + 8 }}
    >
      <button
        id="btn-map-layer"
        onClick={onToggleLayer}
        className={`${btnBase} ${btnInactive} active:scale-95`}
        title={`Switch map layer to ${nextLabel}`}
      >
        <Layers className="w-4 h-4" />
      </button>
      <div className="h-px bg-border/40 mx-1" />
      <button
        id="btn-zoom-in"
        onClick={() => map.zoomIn()}
        className={`${btnBase} ${btnInactive} active:scale-95`}
        title="Zoom in"
      >
        <Plus className="w-4 h-4" />
      </button>
      <button
        id="btn-zoom-out"
        onClick={() => map.zoomOut()}
        className={`${btnBase} ${btnInactive} active:scale-95`}
        title="Zoom out"
      >
        <Minus className="w-4 h-4" />
      </button>
    </div>
  );
}

// ─── Map event tracker ────────────────────────────────────────────────────────
function MapEventsHandler({
  setMapViewport,
}: {
  setMapViewport: (v: { lat: number; lng: number; zoom: number }) => void;
}) {
  const map = useMapEvents({
    moveend: () => {
      const c = map.getCenter();
      setMapViewport({ lat: c.lat, lng: c.lng, zoom: map.getZoom() });
    },
    zoomend: () => {
      const c = map.getCenter();
      setMapViewport({ lat: c.lat, lng: c.lng, zoom: map.getZoom() });
    },
  });
  return null;
}

// ─── Safe Bounds Component ────────────────────────────────────────────────────
function SafeBoundsComponent({ bounds }: { bounds: L.LatLngBounds | null }) {
  const map = useMap();
  useSafeFitBounds(map, bounds);
  return null;
}

// ─── FlyTo Lot Controller ─────────────────────────────────────────────────────
// Listens for the 'landiq:flyto-lot' custom window event dispatched by the
// pill carousel in ReportPanel, then commands the Leaflet map to flyTo the lot.
function FlyToLotController() {
  const map = useMap();

  useEffect(() => {
    const handler = (e: Event) => {
      const { centroid } = (e as CustomEvent).detail ?? {};
      if (!centroid) return;
      const [lat, lng] = centroid as [number, number];
      if (!isNaN(lat) && !isNaN(lng)) {
        try { map.flyTo([lat, lng], 18, { animate: true, duration: 0.8 }); } catch { /* noop */ }
      }
    };
    window.addEventListener('landiq:flyto-lot', handler);
    return () => window.removeEventListener('landiq:flyto-lot', handler);
  }, [map]);

  return null;
}



// ─── COGO Draft Layer ─────────────────────────────────────────────────────────
// Renders the live traverse shape over the true coordinates.
// The spatial shield is 100% CSS blur on the tile pane — no coordinate displacement.
// Map camera flies to the true start location ONCE when coordinates first arrive,
// then stays perfectly still as subsequent legs are typed.

function CogoDraftLayer({
  coords,
  closureGap,
}: {
  coords: [number, number][];
  closureGap: { errorMeters: number; isClosed: boolean } | null;
}) {
  const map = useMap();
  const hasFlewToStart = useRef(false);

  const validCoords = (coords || [])
    .map((c) => [Number(c[0]), Number(c[1])] as [number, number])
    .filter((c) => c && c.length >= 2 && !isNaN(c[0]) && !isNaN(c[1]));

  // Fly to true start location exactly ONCE when first valid coord arrives.
  // After that, the camera is completely still — no shaking on every keystroke.
  useEffect(() => {
    if (hasFlewToStart.current) return;
    if (validCoords.length >= 1) {
      const [lat, lng] = validCoords[0];
      try {
        map.flyTo([lat, lng], 17, { animate: true, duration: 1.2 });
        hasFlewToStart.current = true;
      } catch { /* noop */ }
    }
  }, [validCoords.length >= 1]);

  // Reset the "has flown" flag if user clears their inputs
  useEffect(() => {
    if (validCoords.length === 0) hasFlewToStart.current = false;
  }, [validCoords.length === 0]);

  if (validCoords.length < 2) return null;

  const stationLabels = ["S1","S2","S3","S4","S5","S6","S7","S8","S9","S10",
    "S11","S12","S13","S14","S15","S16","S17","S18","S19","S20"];

  return (
    <>
      {/* Cyan dashed traverse lines */}
      <Polyline
        positions={validCoords}
        pathOptions={{ color: "#06B6D4", weight: 2.5, dashArray: "7 5", opacity: 1 }}
      />

      {/* Red dotted gap line when shape is open */}
      {!closureGap?.isClosed && validCoords.length >= 2 && (
        <Polyline
          positions={[validCoords[validCoords.length - 1], validCoords[0]]}
          pathOptions={{ color: "#EF4444", weight: 1.5, dashArray: "4 7", opacity: 0.8 }}
        />
      )}

      {/* Station vertex markers */}
      {validCoords.map((pos, i) => (
        <CircleMarker
          key={i}
          center={pos}
          radius={5}
          pathOptions={{ color: "#06B6D4", fillColor: "#0f172a", fillOpacity: 1, weight: 2 }}
        >
          <Tooltip
            permanent
            direction="top"
            offset={[0, -8]}
            className="text-[10px] font-bold bg-[#0f172a] text-cyan-300 border-cyan-500/40 px-1.5 py-0.5 rounded shadow-lg"
          >
            {stationLabels[i] ?? `S${i + 1}`}
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}
