import { useEffect } from "react";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useAppContext } from "@/context/AppContext";

export function MapView() {
  const { analysisState } = useAppContext();
  const hasAnalysis = analysisState === 'gate' || analysisState === 'complete';

  const position: [number, number] = [6.5244, 3.3792]; // Lagos, Nigeria
  const polygonCoords: [number, number][] = [
    [6.5250, 3.3790],
    [6.5255, 3.3800],
    [6.5245, 3.3810],
    [6.5235, 3.3805],
    [6.5240, 3.3795]
  ];

  return (
    <div className="absolute inset-0 z-0 bg-[#E5E3DF] dark:bg-[#121212]">
      <MapContainer 
        center={position} 
        zoom={14} 
        zoomControl={false}
        className="w-full h-full"
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        />
        {hasAnalysis && (
          <Polygon 
            positions={polygonCoords} 
            pathOptions={{ 
              color: '#0058BD', 
              weight: 2, 
              fillColor: '#0058BD', 
              fillOpacity: 0.2,
              dashArray: '5, 5'
            }} 
          />
        )}
      </MapContainer>

      {/* Empty State Overlay */}
      {!hasAnalysis && (
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center z-[1000] lg:pr-[420px] lg:pl-[380px] p-6">
          <div className="bg-white/90 dark:bg-[#22262F]/90 backdrop-blur-md p-6 rounded-2xl shadow-lg border border-border max-w-sm w-full text-center pointer-events-auto">
             <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 21.5C12 21.5 20.5 15.5 20.5 9.5C20.5 4.80558 16.6944 1 12 1C7.30558 1 3.5 4.80558 3.5 9.5C3.5 15.5 12 21.5 12 21.5Z" stroke="#0058BD" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M12 12.5C13.6569 12.5 15 11.1569 15 9.5C15 7.84315 13.6569 6.5 12 6.5C10.3431 6.5 9 7.84315 9 9.5C9 11.1569 10.3431 12.5 12 12.5Z" stroke="#0058BD" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
             </div>
             <h3 className="font-medium text-lg text-foreground mb-1">Carfax for Land in Nigeria</h3>
             <p className="text-muted-foreground text-sm">Upload coordinates to begin spatial analysis</p>
          </div>
        </div>
      )}
    </div>
  );
}
