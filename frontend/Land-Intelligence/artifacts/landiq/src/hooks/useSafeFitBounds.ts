import { useLayoutEffect, useEffect } from "react";
import L from "leaflet";

export function useSafeFitBounds(
  map: L.Map | null,
  bounds: L.LatLngBounds | null
) {
  // Layer 2: Synchronous invalidateSize before any bounds calculation
  useLayoutEffect(() => {
    if (!map || !bounds || !bounds.isValid()) return;

    // Force Leaflet to re-read the container's actual pixel dimensions
    map.invalidateSize({ animate: false });

    // Defensive: re-check size AFTER invalidateSize
    const size = map.getSize();
    if (size.x === 0 || size.y === 0) {
      console.warn(
        '[MapView] Container has zero size — deferring fitBounds until layout is ready.'
      );
      return;
    }

    map.fitBounds(bounds, {
      padding: [20, 20],
      maxZoom: 18,
    });
  }, [map, bounds]);

  // Layer 3: Catch transitions when container becomes visible (e.g. mobile tab switches)
  useEffect(() => {
    if (!map || !bounds) return;
    const container = map.getContainer();

    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0 && bounds.isValid()) {
        map.invalidateSize({ animate: false });
        map.fitBounds(bounds, { padding: [20, 20], maxZoom: 18 });
        observer.disconnect(); // fire once, then stop watching
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [map, bounds]);
}
