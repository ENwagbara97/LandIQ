import React from 'react';
import { 
  GraduationCap, 
  HeartPulse, 
  Fuel, 
  ShoppingCart, 
  Route, 
  Store, 
  MapPin, 
  Compass,
  Building2
} from 'lucide-react';

interface Landmark {
  name: string;
  category: string;
  distance_m: number;
  direction: string;
}

interface NearbyLandmarksProps {
  landmarksData?: {
    available?: boolean;
    radius_m?: number;
    landmarks?: Landmark[];
    summary?: string;
  };
}

export function NearbyLandmarksCard({ landmarksData }: NearbyLandmarksProps) {
  if (!landmarksData || !landmarksData.available || !landmarksData.landmarks || landmarksData.landmarks.length === 0) {
    return (
      <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4">
        <div className="flex items-center gap-2 text-xs font-bold text-[var(--report-muted)] uppercase tracking-wider mb-2">
          <MapPin className="w-3.5 h-3.5 text-[var(--secondary)]" />
          <span>Surrounding Context (500m Radius)</span>
        </div>
        <p className="text-xs text-[var(--report-secondary)] italic">
          Surrounding landmark data is unavailable for this parcel location. Verify local amenities during physical ground inspection.
        </p>
      </div>
    );
  }

  const { landmarks, summary, radius_m = 500 } = landmarksData;

  const getCategoryIcon = (category: string) => {
    const catLower = category.toLowerCase();
    if (catLower.includes('school') || catLower.includes('university')) return <GraduationCap className="w-4 h-4 text-blue-500" />;
    if (catLower.includes('hospital') || catLower.includes('clinic')) return <HeartPulse className="w-4 h-4 text-rose-500" />;
    if (catLower.includes('fuel') || catLower.includes('petrol')) return <Fuel className="w-4 h-4 text-amber-500" />;
    if (catLower.includes('market') || catLower.includes('supermarket')) return <ShoppingCart className="w-4 h-4 text-emerald-500" />;
    if (catLower.includes('road')) return <Route className="w-4 h-4 text-indigo-500" />;
    if (catLower.includes('shop')) return <Store className="w-4 h-4 text-teal-500" />;
    return <Building2 className="w-4 h-4 text-slate-400" />;
  };

  return (
    <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-[var(--report-border)]">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-[var(--secondary)]" />
          <span className="text-xs font-bold text-[var(--report-muted)] uppercase tracking-wider">
            Nearby Context (Within {radius_m}m)
          </span>
        </div>
        <span className="text-[10px] font-mono text-[var(--report-muted)]">
          {landmarks.length} Identified POIs
        </span>
      </div>

      <div className="space-y-2 mb-3">
        {landmarks.map((lm, idx) => (
          <div key={idx} className="flex items-center justify-between text-xs py-1.5 border-b border-[var(--report-border)] last:border-0">
            <div className="flex items-center gap-2.5 min-w-0 pr-2">
              <span className="flex-shrink-0">{getCategoryIcon(lm.category)}</span>
              <span className="font-medium text-[var(--report-text)] truncate">{lm.name}</span>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0 font-mono text-xs text-[var(--report-secondary)]">
              <span>{lm.distance_m}m</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 font-bold text-[var(--report-text)]">
                {lm.direction}
              </span>
            </div>
          </div>
        ))}
      </div>

      {summary && (
        <div className="mt-3 pt-2.5 border-t border-[var(--report-border)] text-xs text-[var(--report-secondary)] leading-relaxed italic">
          {summary}
        </div>
      )}
    </div>
  );
}
