import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import { NavigationData, Coordinate } from '../../types/navigation';
import { useScreenWakeLock } from '../../hooks/useScreenWakeLock';
import { useRouteCalculation } from '../../hooks/useRouteCalculation';
import { Navigation2, Car, Footprints, AlertCircle, MapPin, Loader2, X, Globe, Copy, Share2, ExternalLink, Check } from 'lucide-react';
import { SiteInspectionChecklist } from './SiteInspectionChecklist';
import { MapErrorBoundary } from '../map/MapErrorBoundary';

// Custom Icons
const createPulseIcon = () => L.divIcon({
  className: 'gps-pulse-icon',
  html: `<div style="position:relative; width:16px; height:16px;">
          <div style="position:absolute; width:16px; height:16px; background-color:#3B82F6; border-radius:50%; border:2px solid white; z-index:2;"></div>
          <div style="position:absolute; width:16px; height:16px; background-color:#3B82F6; border-radius:50%; animation: gps-pulse 2s infinite ease-out; z-index:1;"></div>
         </div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8]
});

const createTimeChipIcon = (timeLabel: string) => L.divIcon({
  className: 'time-chip-icon',
  html: `<div class="bg-blue-600 text-white text-xs font-bold px-2 py-1 rounded-full shadow-md border border-white whitespace-nowrap">${timeLabel}</div>`,
  iconAnchor: [20, 10]
});

const redPinIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  shadowSize: [41, 41]
});

// Helper to calculate polyline geometric midpoint
const getPolylineMidpoint = (coords: [number, number][]): [number, number] | null => {
  if (!coords || coords.length === 0) return null;
  const midIndex = Math.floor(coords.length / 2);
  return coords[midIndex];
};

interface PanelProps {
  navData: NavigationData;
  reportData: any; // Full report data needed for the checklist
  onClose: () => void;
  onArrivalComplete: () => void; // Triggered when API succeeds
}

export function SiteNavigationPanel({ navData, reportData, onClose, onArrivalComplete }: PanelProps) {
  // WakeLock
  const { isLocked, unsupported } = useScreenWakeLock();
  
  // Routing
  const { route, isLoading, error: routeError, calculateRoute } = useRouteCalculation();
  const [routeMode, setRouteMode] = useState<'driving' | 'walking'>('driving');
  
  // GPS State
  const [currentPos, setCurrentPos] = useState<Coordinate | null>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [showChecklist, setShowChecklist] = useState(false);

  // Draggable Bottom Sheet State (Mobile)
  const [panelHeight, setPanelHeight] = useState(window.innerHeight * 0.35);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartY = useRef(0);
  const startHeight = useRef(0);

  const handleDragStart = (clientY: number) => {
    setIsDragging(true);
    dragStartY.current = clientY;
    startHeight.current = panelHeight;
  };

  const handleDragMove = (clientY: number) => {
    if (!isDragging) return;
    const deltaY = dragStartY.current - clientY;
    const newHeight = startHeight.current + deltaY;
    const vh = window.innerHeight;
    const clamped = Math.max(vh * 0.15, Math.min(newHeight, vh * 0.85));
    setPanelHeight(clamped);
  };

  const handleDragEnd = () => {
    if (!isDragging) return;
    setIsDragging(false);
    const vh = window.innerHeight;
    if (panelHeight > vh * 0.6) setPanelHeight(vh * 0.85);
    else if (panelHeight < vh * 0.25) setPanelHeight(vh * 0.15);
    else setPanelHeight(vh * 0.35);
  };

  
  // Refs for Fix B1 and B2
  const hasArrivedRef = useRef(false);
  const lastStateUpdateTimeRef = useRef<number>(0);
  const gpsMarkerRef = useRef<L.Marker>(null);
  const mapRef = useRef<L.Map | null>(null);

  // Initialize Route when we get the first GPS fix
  useEffect(() => {
    if (currentPos && !route && !isLoading && !routeError) {
      calculateRoute(
        currentPos, 
        { lat: navData.centroid_lat, lng: navData.centroid_lng },
        routeMode
      );
    }
  }, [currentPos, route, isLoading, routeError, calculateRoute, navData, routeMode]);

  // Handle Mode Switch
  const handleModeSwitch = (mode: 'driving' | 'walking') => {
    if (mode !== routeMode) {
      setRouteMode(mode);
      if (currentPos) {
        calculateRoute(
          currentPos,
          { lat: navData.centroid_lat, lng: navData.centroid_lng },
          mode
        );
      }
    }
  };

  // Diaspora Location State
  const [isDiaspora, setIsDiaspora] = useState(false);
  const [copiedCoords, setCopiedCoords] = useState(false);
  const diasporaPingSentRef = useRef(false);

  const isInsideNigeria = (lat: number, lng: number): boolean => {
    return lat >= 4.0 && lat <= 14.0 && lng >= 2.5 && lng <= 15.5;
  };

  // GPS Tracking Loop
  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setGpsError("Geolocation is not supported by your browser.");
      return;
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords;

        // DIASPORA BOUNDING BOX GUARD
        if (!isInsideNigeria(latitude, longitude)) {
          setIsDiaspora(true);
          if (!diasporaPingSentRef.current && navData?.report_id) {
            diasporaPingSentRef.current = true;
            fetch(`/api/sessions/${navData.report_id}/diaspora-ping`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ country: "Overseas" })
            }).catch(() => {});
          }
          return; // Do NOT calculate route or move user marker across oceans
        }

        const newPos = { lat: latitude, lng: longitude };
        
        // FIX B2: Move the marker instantly without triggering a React re-render
        if (gpsMarkerRef.current) {
          gpsMarkerRef.current.setLatLng([latitude, longitude]);
        }

        // FIX B2: Throttle React state updates to 2 seconds to prevent massive tile re-renders
        const now = Date.now();
        if (now - lastStateUpdateTimeRef.current > 2000) {
          setCurrentPos(newPos);
          lastStateUpdateTimeRef.current = now;
        }

        // FIX B1: Strict Arrival Geo-Fence Check
        if (!hasArrivedRef.current) {
          // Haversine distance
          const R = 6371e3;
          const dLat = (navData.centroid_lat - latitude) * Math.PI / 180;
          const dLng = (navData.centroid_lng - longitude) * Math.PI / 180;
          const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                    Math.cos(latitude * Math.PI / 180) * Math.cos(navData.centroid_lat * Math.PI / 180) *
                    Math.sin(dLng/2) * Math.sin(dLng/2);
          const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
          const distanceM = R * c;

          if (distanceM <= navData.arrival_radius_m) {
            hasArrivedRef.current = true; // Block future calls immediately
            
            // Fire API call exactly once
            fetch(`/api/reports/${navData.report_id}/arrival`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                arrived_at: new Date().toISOString(),
                distance_from_centroid_m: distanceM
              })
            }).then(res => {
              if (res.ok) {
                setShowChecklist(true);
                onArrivalComplete();
              }
            }).catch(err => console.error("Arrival API failed:", err));
          }
        }
      },
      (err) => {
        setGpsError(`GPS Error: ${err.message}`);
      },
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 5000 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [navData]);

  // Format Duration
  const formatDuration = (seconds: number) => {
    const mins = Math.ceil(seconds / 60);
    if (mins >= 60) {
      const hrs = Math.floor(mins / 60);
      return `${hrs} hr ${mins % 60} min`;
    }
    return `${mins} min`;
  };

  const midpoint = route ? getPolylineMidpoint(route.geometry) : null;

  return (
    <>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes gps-pulse {
          0% { transform: scale(1); opacity: 1; }
          100% { transform: scale(3); opacity: 0; }
        }
        .gps-pulse-icon { overflow: visible !important; }
      `}} />

      {/* Main Overlay */}
      <div className="fixed inset-0 z-[300] bg-black animate-in slide-in-from-bottom sm:slide-in-from-right duration-300">
        
        {/* Map Container */}
        <div className="absolute inset-0 z-0">
          <button 
            onClick={onClose}
            className="absolute top-4 left-4 z-[400] bg-[var(--report-surface)] p-2 rounded-full shadow-md text-[var(--report-secondary)] hover:text-[var(--report-text)] border border-[var(--report-border)] flex items-center justify-center"
          >
            <X className="w-5 h-5" />
          </button>
          
          {/* WakeLock Status Indicator */}
          <div className="absolute top-4 right-4 z-[400] flex flex-col items-end space-y-2">
            {!isLocked && unsupported && (
              <div className="bg-amber-100 text-amber-800 text-xs px-3 py-1.5 rounded-full shadow-sm flex items-center border border-amber-200">
                <AlertCircle className="w-3 h-3 mr-1" />
                Keep screen awake manually
              </div>
            )}
            {gpsError && (
              <div className="bg-red-100 text-red-800 text-xs px-3 py-1.5 rounded-full shadow-sm flex items-center border border-red-200">
                <AlertCircle className="w-3 h-3 mr-1" />
                {gpsError}
              </div>
            )}
          </div>

          <MapErrorBoundary>
            <MapContainer 
              center={[navData.centroid_lat, navData.centroid_lng]} 
              zoom={16} 
              className="w-full h-full z-0"
              ref={mapRef}
              zoomControl={false}
            >
              <TileLayer
                url="https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}"
                subdomains={["mt0", "mt1", "mt2", "mt3"]}
                maxZoom={24}
                maxNativeZoom={20}
                attribution="Google Hybrid"
              />
              
              {/* System Red Boundary (Target) */}
              <Polyline 
                positions={navData.polygon_wgs84} 
                pathOptions={{ color: '#ef4444', weight: 3, fillOpacity: 0.1, fillColor: '#ef4444' }} 
              />
              <Marker position={[navData.centroid_lat, navData.centroid_lng]} icon={redPinIcon} />

              {/* GPS User Dot */}
              {currentPos && (
                <Marker 
                  position={[currentPos.lat, currentPos.lng]} 
                  icon={createPulseIcon()} 
                  ref={gpsMarkerRef as any}
                  zIndexOffset={1000}
                />
              )}

              {/* Route Polyline (FIX B4/B5) */}
              {route && (
                <>
                  <Polyline 
                    positions={route.geometry} 
                    pathOptions={{ 
                      color: route.fallback_used === 'straight_line' ? '#a855f7' : '#3b82f6', 
                      weight: 6, 
                      opacity: 0.8,
                      dashArray: route.fallback_used === 'straight_line' ? '10, 10' : undefined
                    }} 
                  />
                  {/* Floating Time Chip at Midpoint */}
                  {midpoint && (
                    <Marker 
                      position={midpoint} 
                      icon={createTimeChipIcon(formatDuration(route.duration_s))} 
                    />
                  )}
                </>
              )}

              {/* Auto-Fit Bounds logic */}
              {(() => {
                 // A small inner component to access useMap safely
                 const FitBounds = () => {
                   const map = useMap();
                   useEffect(() => {
                     if (currentPos && navData) {
                       const bounds = L.latLngBounds([
                         [currentPos.lat, currentPos.lng],
                         [navData.centroid_lat, navData.centroid_lng]
                       ]);
                       map.fitBounds(bounds, { padding: [50, 50], animate: true });
                     }
                   }, [currentPos, navData, map]);
                   return null;
                 };
                 return <FitBounds />;
              })()}

            </MapContainer>
          </MapErrorBoundary>
        </div>

        {/* Bottom / Side Panel */}
        <div 
          className="absolute bottom-0 left-0 right-0 sm:top-0 sm:bottom-0 sm:right-0 sm:left-auto sm:w-96 bg-[var(--report-bg)] text-[var(--report-text)] shadow-[0_-10px_40px_rgba(0,0,0,0.3)] sm:shadow-[-4px_0_6px_-1px_rgba(0,0,0,0.1)] z-[310] flex flex-col sm:border-l border-[var(--report-border)] font-[var(--report-body)] rounded-t-[24px] sm:rounded-none overflow-hidden"
          style={{ height: window.innerWidth < 640 ? `${panelHeight}px` : '100%', transition: isDragging ? 'none' : 'height 0.3s cubic-bezier(0.25, 1, 0.5, 1)' }}
        >
          {/* Draggable Header Area (Handle + Title) */}
          <div 
            className="w-full shrink-0 touch-none bg-[var(--report-bg)] cursor-grab active:cursor-grabbing sm:cursor-auto"
            onTouchStart={(e) => handleDragStart(e.touches[0].clientY)}
            onTouchMove={(e) => handleDragMove(e.touches[0].clientY)}
            onTouchEnd={handleDragEnd}
            onMouseDown={(e) => handleDragStart(e.clientY)}
            onMouseMove={(e) => handleDragMove(e.clientY)}
            onMouseUp={handleDragEnd}
            onMouseLeave={handleDragEnd}
          >
            {/* Drag Handle for Mobile */}
            <div className="w-full pt-3 pb-2 flex justify-center sm:hidden">
              <div className="w-12 h-1.5 bg-[var(--report-muted)] opacity-30 rounded-full" />
            </div>

            <div className="px-4 pb-4 border-b border-[var(--report-border)] sm:pt-4">
              <h3 className="font-bold text-lg text-[var(--report-text)] line-clamp-1 select-none pointer-events-none">{navData.lga}, {navData.state}</h3>
              <p className="text-sm text-[var(--report-secondary)] flex items-center mt-1 select-none pointer-events-none">
                <MapPin className="w-3 h-3 mr-1" />
                Target: {navData.stated_area_sqm.toLocaleString()} sqm Parcel
              </p>
            </div>
          </div>

          <div className="flex-1 p-4 overflow-y-auto bg-[var(--report-bg)]">
            {isDiaspora ? (
              <div className="space-y-4">
                <div className="rounded-[12px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4">
                  <div className="flex items-center gap-2.5 mb-2">
                    <Globe className="w-5 h-5 text-blue-500" />
                    <h4 className="font-bold text-sm text-[var(--report-text)]">Viewing From Overseas</h4>
                  </div>
                  <p className="text-xs text-[var(--report-secondary)] leading-relaxed mb-4">
                    Live turn-by-turn site navigation is available when on site in Nigeria. Use the tools below to copy coordinates or dispatch field instructions to your local surveyor or representative.
                  </p>

                  <div className="space-y-2">
                    {/* Copy Coords */}
                    <button
                      onClick={() => {
                        const coordStr = `${navData.centroid_lat.toFixed(5)}°N, ${navData.centroid_lng.toFixed(5)}°E`;
                        navigator.clipboard.writeText(coordStr);
                        setCopiedCoords(true);
                        setTimeout(() => setCopiedCoords(false), 2000);
                      }}
                      className="w-full flex items-center justify-between px-3 py-2.5 rounded-[8px] bg-[var(--report-bg)] border border-[var(--report-border)] text-xs font-semibold text-[var(--report-text)] hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        {copiedCoords ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4 text-[var(--secondary)]" />}
                        <span>{copiedCoords ? "Coordinates Copied!" : "Copy Parcel Coordinates"}</span>
                      </div>
                      <span className="font-mono text-[10px] text-[var(--report-muted)]">
                        {navData.centroid_lat.toFixed(4)}, {navData.centroid_lng.toFixed(4)}
                      </span>
                    </button>

                    {/* WhatsApp Dispatch */}
                    <button
                      onClick={() => {
                        const reportUrl = window.location.origin + (navData.report_id ? `/#report-${navData.report_id}` : '');
                        const msg = encodeURIComponent(
                          `Hello, please inspect this land parcel for me in ${navData.lga}, ${navData.state}:\n\n` +
                          `Location: ${navData.centroid_lat.toFixed(5)}°N, ${navData.centroid_lng.toFixed(5)}°E\n` +
                          `LandIQ Report: ${reportUrl}\n\n` +
                          `Please confirm boundary beacons and physical road access matching this report.`
                        );
                        window.open(`https://wa.me/?text=${msg}`, '_blank');
                      }}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-[8px] bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-sm transition-colors"
                    >
                      <Share2 className="w-4 h-4" />
                      <span>Share Dispatch Message via WhatsApp</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* Travel Modes */}
                <div className="flex bg-[var(--report-surface)] border border-[var(--report-border)] p-1 rounded-[10px] mb-6">
                  <button
                    onClick={() => handleModeSwitch('driving')}
                    className={`flex-1 flex items-center justify-center py-2 text-sm font-medium rounded-[8px] transition-colors ${routeMode === 'driving' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-[var(--report-secondary)] hover:text-[var(--report-text)]'}`}
                  >
                    <Car className="w-4 h-4 mr-2" />
                    Drive
                  </button>
                  <button
                    onClick={() => handleModeSwitch('walking')}
                    className={`flex-1 flex items-center justify-center py-2 text-sm font-medium rounded-[8px] transition-colors ${routeMode === 'walking' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-[var(--report-secondary)] hover:text-[var(--report-text)]'}`}
                  >
                    <Footprints className="w-4 h-4 mr-2" />
                    Walk
                  </button>
                </div>

                {/* Route Info */}
                {isLoading && (
                  <div className="flex flex-col items-center justify-center py-8 text-[var(--report-muted)]">
                    <Loader2 className="w-6 h-6 animate-spin mb-2" />
                    <p className="text-sm">Calculating route...</p>
                  </div>
                )}
                
                {!isLoading && route && (
                  <div className="bg-[var(--report-surface)] rounded-[10px] p-4 shadow-sm border border-[var(--report-border)]">
                    <div className="flex justify-between items-end mb-2">
                      <div className="text-3xl font-bold text-green-600 dark:text-green-400">
                        {formatDuration(route.duration_s)}
                      </div>
                      <div className="text-[var(--report-secondary)] font-medium pb-1">
                        {(route.distance_m / 1000).toFixed(1)} km
                      </div>
                    </div>
                    
                    {route.fallback_used === 'straight_line' && (
                      <div className="mt-3 bg-amber-50 text-amber-800 text-xs p-2 rounded flex items-start border border-amber-200">
                        <AlertCircle className="w-4 h-4 mr-2 shrink-0 mt-0.5" />
                        <span>Road network not mapped here. Showing direct compass bearing.</span>
                      </div>
                    )}
                  </div>
                )}

                {!isLoading && !route && currentPos && (
                  <div className="text-sm text-[var(--report-muted)] text-center py-4">
                    Unable to find route.
                  </div>
                )}
                
                {!currentPos && (
                  <div className="text-sm text-[var(--report-muted)] text-center py-8 flex flex-col items-center">
                    <Navigation2 className="w-6 h-6 text-blue-400 mb-2 animate-pulse" />
                    Acquiring GPS Signal...
                  </div>
                )}
              </>
            )}
          </div>

          <div className="p-4 bg-[var(--report-surface)] border-t border-[var(--report-border)] shrink-0">
            <a 
              href={`https://www.google.com/maps/dir/?api=1&destination=${navData.centroid_lat},${navData.centroid_lng}`}
              target="_blank"
              rel="noreferrer"
              className="w-full flex items-center justify-center h-11 bg-[var(--report-bg)] hover:bg-[var(--report-bg)]/80 text-[var(--report-text)] border border-[var(--report-border)] font-bold rounded-[10px] transition-colors text-sm"
            >
              Open in Google Maps
            </a>
          </div>
        </div>
      </div>

      {/* Checklist Modal */}
      {showChecklist && (
        <SiteInspectionChecklist 
          reportData={reportData} 
          onClose={() => {
            setShowChecklist(false);
            onClose(); // Close the entire navigation panel after acknowledging
          }} 
        />
      )}
    </>
  );
}
