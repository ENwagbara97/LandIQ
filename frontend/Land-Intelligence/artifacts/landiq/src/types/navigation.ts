export interface Coordinate {
  lat: number;
  lng: number;
}

export interface NavigationData {
  report_id: string;
  centroid_lat: number;
  centroid_lng: number;
  polygon_wgs84: [number, number][];
  arrival_radius_m: number;
  lga: string;
  state: string;
  stated_area_sqm: number;
}

export interface OSRMRoute {
  distance_m: number;
  duration_s: number;
  geometry: [number, number][]; // decoded polyline [lat, lng]
  mode: 'driving' | 'walking';
  fallback_used?: 'geoapify' | 'straight_line';
}
