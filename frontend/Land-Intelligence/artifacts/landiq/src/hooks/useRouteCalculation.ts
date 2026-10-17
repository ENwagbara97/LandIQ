import { useState, useCallback } from 'react';
import { Coordinate, OSRMRoute } from '../types/navigation';

const haversineDistance = (coord1: Coordinate, coord2: Coordinate) => {
  const toRad = (x: number) => (x * Math.PI) / 180;
  const R = 6371e3; // metres
  const dLat = toRad(coord2.lat - coord1.lat);
  const dLng = toRad(coord2.lng - coord1.lng);
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(toRad(coord1.lat)) * Math.cos(toRad(coord2.lat)) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
};

// Decodes OSRM polyline strings (simplified version for typical geometry)
function decodePolyline(str: string, precision: number = 5): [number, number][] {
    let index = 0, lat = 0, lng = 0, coordinates: [number, number][] = [];
    let shift = 0, result = 0, byte = null, latitude_change, longitude_change, factor = Math.pow(10, precision);

    while (index < str.length) {
        byte = null; shift = 0; result = 0;
        do {
            byte = str.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);
        latitude_change = ((result & 1) ? ~(result >> 1) : (result >> 1));
        shift = result = 0;
        do {
            byte = str.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);
        longitude_change = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lat += latitude_change; lng += longitude_change;
        coordinates.push([lat / factor, lng / factor]);
    }
    return coordinates;
}

export function useRouteCalculation() {
  const [route, setRoute] = useState<OSRMRoute | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const calculateRoute = useCallback(async (start: Coordinate, end: Coordinate, mode: 'driving' | 'walking' = 'driving') => {
    setIsLoading(true);
    setError(null);
    
    // OSRM expects coordinates in lng,lat format
    const profile = mode === 'driving' ? 'driving' : 'foot';
    const osrmUrl = `https://router.project-osrm.org/route/v1/${profile}/${start.lng},${start.lat};${end.lng},${end.lat}?overview=full`;

    try {
      // 1. Try Primary: OSRM
      const res = await fetch(osrmUrl);
      if (!res.ok) throw new Error('OSRM Failed');
      
      const data = await res.json();
      if (data.code !== 'Ok' || !data.routes || data.routes.length === 0) {
        throw new Error('OSRM No Route Found');
      }

      const r = data.routes[0];
      setRoute({
        distance_m: r.distance,
        duration_s: r.duration,
        geometry: decodePolyline(r.geometry),
        mode,
      });

    } catch (osrmError) {
      console.warn('OSRM failed, cascading to fallback...', osrmError);
      
      // 2. Try Secondary: Geoapify (if API key is present)
      const geoapifyKey = import.meta.env.VITE_GEOAPIFY_API_KEY;
      if (geoapifyKey) {
        try {
          const gMode = mode === 'driving' ? 'drive' : 'walk';
          const geoUrl = `https://api.geoapify.com/v1/routing?waypoints=${start.lat},${start.lng}|${end.lat},${end.lng}&mode=${gMode}&apiKey=${geoapifyKey}`;
          const gRes = await fetch(geoUrl);
          if (!gRes.ok) throw new Error('Geoapify Failed');
          const gData = await gRes.json();
          
          if (gData.features && gData.features.length > 0) {
            const props = gData.features[0].properties;
            const geom = gData.features[0].geometry.coordinates; // Geoapify returns GeoJSON [[[lng, lat], ...]]
            
            // Convert GeoJSON [[lng, lat]] to Leaflet [[lat, lng]]
            let mappedGeom: [number, number][] = [];
            if (geom && geom.length > 0) {
              const lineString = geom[0];
              mappedGeom = lineString.map((coord: number[]) => [coord[1], coord[0]]);
            }

            setRoute({
              distance_m: props.distance,
              duration_s: props.time,
              geometry: mappedGeom,
              mode,
              fallback_used: 'geoapify'
            });
            setIsLoading(false);
            return;
          }
        } catch (geoError) {
          console.warn('Geoapify failed, cascading to Straight Line...', geoError);
        }
      }

      // 3. Final Fallback: Straight Line (Haversine)
      const dist = haversineDistance(start, end);
      // Rough duration estimate: Walking 1.4m/s, Driving ~8.3m/s (30km/h in unknown terrain)
      const speed = mode === 'walking' ? 1.4 : 8.3;
      
      setRoute({
        distance_m: dist,
        duration_s: dist / speed,
        geometry: [
          [start.lat, start.lng],
          [end.lat, end.lng]
        ],
        mode,
        fallback_used: 'straight_line'
      });
    }

    setIsLoading(false);
  }, []);

  return { route, isLoading, error, calculateRoute };
}
