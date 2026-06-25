import { useState } from "react";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useAppContext } from "@/context/AppContext";
import { Layers, Plus, Minus } from "lucide-react";
import { useMap } from "react-leaflet";

function ZoomControls() {
  const map = useMap();
  return (
    <div className="absolute right-3 z-[500] flex flex-col gap-1" style={{ top: 72 }}>
      {/* Layer toggle */}
      <button
        id="layer-toggle-btn"
        className="w-9 h-9 bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-sm rounded-full shadow-md border border-border flex items-center justify-center hover:bg-muted transition-colors"
        title="Toggle satellite"
      >
        <Layers className="w-4 h-4 text-foreground" />
      </button>
      {/* Zoom in */}
      <button
        onClick={() => map.zoomIn()}
        className="w-9 h-9 bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-sm rounded-full shadow-md border border-border flex items-center justify-center hover:bg-muted transition-colors"
        title="Zoom in"
      >
        <Plus className="w-4 h-4 text-foreground" />
      </button>
      {/* Zoom out */}
      <button
        onClick={() => map.zoomOut()}
        className="w-9 h-9 bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-sm rounded-full shadow-md border border-border flex items-center justify-center hover:bg-muted transition-colors"
        title="Zoom out"
      >
        <Minus className="w-4 h-4 text-foreground" />
      </button>
    </div>
  );
}

export function MapView() {
  const { analysisState } = useAppContext();
  const hasAnalysis = analysisState === "gate" || analysisState === "complete";
  const [tileStyle, setTileStyle] = useState<"osm" | "satellite">("osm");

  const position: [number, number] = [6.5244, 3.3792];
  const polygonCoords: [number, number][] = [
    [6.525, 3.379],
    [6.5255, 3.38],
    [6.5245, 3.381],
    [6.5235, 3.3805],
    [6.524, 3.3795],
  ];

  const tiles = {
    osm: {
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
    satellite: {
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      attribution: "Tiles &copy; Esri",
    },
  };

  return (
    <div className="absolute inset-0 z-0">
      <MapContainer
        center={position}
        zoom={14}
        zoomControl={false}
        className="w-full h-full"
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          url={tiles[tileStyle].url}
          attribution={tiles[tileStyle].attribution}
          maxZoom={19}
        />

        {/* Custom zoom + layer controls rendered inside map context */}
        <ZoomControlsWrapper
          tileStyle={tileStyle}
          onToggleTile={() =>
            setTileStyle((s) => (s === "osm" ? "satellite" : "osm"))
          }
        />

        {hasAnalysis && (
          <Polygon
            positions={polygonCoords}
            pathOptions={{
              color: "#0058BD",
              weight: 2.5,
              fillColor: "#0058BD",
              fillOpacity: 0.18,
              dashArray: "6, 4",
            }}
          />
        )}
      </MapContainer>

      {/* Empty State */}
      {!hasAnalysis && (
        <div
          className="absolute inset-0 pointer-events-none flex items-end justify-center z-[400] px-6"
          style={{ paddingBottom: 180 }}
        >
          <div className="lg:hidden bg-white/92 dark:bg-[#1E2128]/92 backdrop-blur-md px-5 py-4 rounded-2xl shadow-lg border border-border/60 max-w-[280px] w-full text-center pointer-events-auto">
            <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-2.5">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 21.5C12 21.5 20.5 15.5 20.5 9.5C20.5 4.80558 16.6944 1 12 1C7.30558 1 3.5 4.80558 3.5 9.5C3.5 15.5 12 21.5 12 21.5Z"
                  stroke="#0058BD"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M12 12.5C13.6569 12.5 15 11.1569 15 9.5C15 7.84315 13.6569 6.5 12 6.5C10.3431 6.5 9 7.84315 9 9.5C9 11.1569 10.3431 12.5 12 12.5Z"
                  stroke="#0058BD"
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

          {/* Desktop empty state — centered in map without sidebar offsets */}
          <div className="hidden lg:block bg-white/92 dark:bg-[#1E2128]/92 backdrop-blur-md px-5 py-4 rounded-2xl shadow-lg border border-border/60 max-w-[280px] w-full text-center pointer-events-auto">
            <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-2.5">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 21.5C12 21.5 20.5 15.5 20.5 9.5C20.5 4.80558 16.6944 1 12 1C7.30558 1 3.5 4.80558 3.5 9.5C3.5 15.5 12 21.5 12 21.5Z"
                  stroke="#0058BD"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M12 12.5C13.6569 12.5 15 11.1569 15 9.5C15 7.84315 13.6569 6.5 12 6.5C10.3431 6.5 9 7.84315 9 9.5C9 11.1569 10.3431 12.5 12 12.5Z"
                  stroke="#0058BD"
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

// Wrapper that uses useMap inside MapContainer context
function ZoomControlsWrapper({
  tileStyle,
  onToggleTile,
}: {
  tileStyle: "osm" | "satellite";
  onToggleTile: () => void;
}) {
  const map = useMap();
  return (
    <div
      className="absolute right-3 z-[500] flex flex-col gap-1.5"
      style={{ top: 72 }}
    >
      <button
        onClick={onToggleTile}
        className="w-9 h-9 bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-sm rounded-full shadow-md border border-border flex items-center justify-center hover:bg-muted transition-colors"
        title={tileStyle === "osm" ? "Switch to satellite" : "Switch to map"}
      >
        <Layers className="w-4 h-4 text-foreground" />
      </button>
      <button
        onClick={() => map.zoomIn()}
        className="w-9 h-9 bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-sm rounded-full shadow-md border border-border flex items-center justify-center hover:bg-muted transition-colors font-bold text-foreground"
        title="Zoom in"
      >
        <Plus className="w-4 h-4" />
      </button>
      <button
        onClick={() => map.zoomOut()}
        className="w-9 h-9 bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-sm rounded-full shadow-md border border-border flex items-center justify-center hover:bg-muted transition-colors font-bold text-foreground"
        title="Zoom out"
      >
        <Minus className="w-4 h-4" />
      </button>
    </div>
  );
}
