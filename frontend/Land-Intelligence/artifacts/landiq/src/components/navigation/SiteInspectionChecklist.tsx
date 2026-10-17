import React from 'react';
import { ShieldCheck, Droplets, Map, Ruler, TreePine, AlertTriangle } from 'lucide-react';

interface ChecklistProps {
  reportData: any; // We use any here to avoid importing the huge ReportSchema if not needed, or we can type it roughly
  onClose: () => void;
}

export function SiteInspectionChecklist({ reportData, onClose }: ChecklistProps) {
  // Extracting key metrics safely
  const statedArea = reportData?.parcel_details?.stated_area_sqm || 0;
  const computedArea = reportData?.parcel_details?.computed_area_ha ? reportData.parcel_details.computed_area_ha * 10000 : 0;
  const floodRisk = reportData?.risk_assessment?.flood_risk?.risk_level?.toLowerCase() || 'low';
  const roadDistance = reportData?.risk_assessment?.accessibility?.distance_to_nearest_road_m || 0;
  
  // Plain English Area Analogy
  const getAreaAnalogy = (sqm: number) => {
    if (sqm <= 0) return 'an unknown size';
    if (sqm < 500) return 'about the size of a basketball court';
    if (sqm < 1500) return 'roughly 4 tennis courts';
    if (sqm < 5000) return 'about the size of a football field';
    return `roughly ${Math.round(sqm / 5000)} football fields`;
  };

  return (
    <div className="fixed inset-0 z-[400] flex items-end justify-center sm:items-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-300 font-[var(--report-body)]">
      <div className="bg-[var(--report-bg)] text-[var(--report-text)] w-full max-w-lg rounded-t-[10px] sm:rounded-[10px] shadow-2xl overflow-hidden flex flex-col max-h-[90vh] border border-[var(--report-border)]">
        
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-700 p-6 text-white shrink-0 relative">
          <div className="absolute top-4 right-4 flex space-x-2">
            <button 
              onClick={onClose}
              className="p-2 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
            >
              ✕
            </button>
          </div>
          <div className="flex items-center space-x-3 mb-2">
            <ShieldCheck className="w-6 h-6 text-green-300" />
            <h2 className="text-lg font-bold">You've Arrived</h2>
          </div>
          <p className="text-xs text-blue-100">
            You are now on-site. Satellite data is helpful, but your physical observations now supersede the digital report. Please verify the following:
          </p>
        </div>

        {/* Scrollable Checklist */}
        <div className="p-6 overflow-y-auto space-y-4 flex-1 bg-[var(--report-bg)]">
          
          {/* Area Check */}
          <div className="bg-[var(--report-surface)] p-4 rounded-[10px] border border-[var(--report-border)] shadow-sm flex items-start space-x-4">
            <div className="bg-blue-500/10 p-2 rounded-lg text-blue-600 dark:text-blue-400 mt-1">
              <Ruler className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-[var(--report-text)]">Physical Boundaries</h4>
              <p className="text-xs text-[var(--report-secondary)] mt-1">
                The document claims {statedArea.toLocaleString()} sqm ({getAreaAnalogy(statedArea)}).
                Walk the perimeter. Are the boundary pegs (beacons) clearly visible and do they match this rough size?
              </p>
              <label className="flex items-center space-x-2 mt-3 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 text-blue-600 rounded border-[var(--report-border)] focus:ring-blue-500 bg-[var(--report-bg)]" />
                <span className="text-[11px] font-bold text-[var(--report-text)] uppercase tracking-wide">Boundaries verified</span>
              </label>
            </div>
          </div>

          {/* Conditional: Flood Check */}
          {(floodRisk === 'high' || floodRisk === 'extreme') && (
            <div className="bg-[var(--report-surface)] p-4 rounded-[10px] border border-red-500/30 shadow-sm flex items-start space-x-4">
              <div className="bg-red-500/10 p-2 rounded-lg text-red-600 dark:text-red-400 mt-1">
                <Droplets className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-red-600 dark:text-red-400">High Flood Risk Detected</h4>
                <p className="text-xs text-[var(--report-secondary)] mt-1">
                  Satellites indicate high flood risk here. Look for watermarks on nearby walls, damp soil, or ask locals about the last rainy season.
                </p>
                <label className="flex items-center space-x-2 mt-3 cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 text-red-600 rounded border-[var(--report-border)] focus:ring-red-500 bg-[var(--report-bg)]" />
                  <span className="text-[11px] font-bold text-[var(--report-text)] uppercase tracking-wide">Flood markers checked</span>
                </label>
              </div>
            </div>
          )}

          {/* Conditional: Road Access Check */}
          {roadDistance > 500 && (
            <div className="bg-[var(--report-surface)] p-4 rounded-[10px] border border-amber-500/30 shadow-sm flex items-start space-x-4">
              <div className="bg-amber-500/10 p-2 rounded-lg text-amber-600 dark:text-amber-400 mt-1">
                <Map className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-amber-600 dark:text-amber-400">Remote Access Warning</h4>
                <p className="text-xs text-[var(--report-secondary)] mt-1">
                  The nearest mapped road is {roadDistance}m away. Is there an unmapped dirt road leading here, or is the land landlocked by other plots?
                </p>
                <label className="flex items-center space-x-2 mt-3 cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 text-amber-600 rounded border-[var(--report-border)] focus:ring-amber-500 bg-[var(--report-bg)]" />
                  <span className="text-[11px] font-bold text-[var(--report-text)] uppercase tracking-wide">Access verified</span>
                </label>
              </div>
            </div>
          )}

          {/* General Topography */}
          <div className="bg-[var(--report-surface)] p-4 rounded-[10px] border border-[var(--report-border)] shadow-sm flex items-start space-x-4">
            <div className="bg-emerald-500/10 p-2 rounded-lg text-emerald-600 dark:text-emerald-400 mt-1">
              <TreePine className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-[var(--report-text)]">Topography & Encroachment</h4>
              <p className="text-xs text-[var(--report-secondary)] mt-1">
                Is the land swampy, rocky, or sloped? Are there any informal structures, fences, or farms encroaching on the boundary?
              </p>
              <label className="flex items-center space-x-2 mt-3 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 text-emerald-600 rounded border-[var(--report-border)] focus:ring-emerald-500 bg-[var(--report-bg)]" />
                <span className="text-[11px] font-bold text-[var(--report-text)] uppercase tracking-wide">Topography verified</span>
              </label>
            </div>
          </div>

        </div>
        
        {/* Footer */}
        <div className="p-4 bg-[var(--report-surface)] border-t border-[var(--report-border)] shrink-0">
          <button 
            onClick={onClose}
            className="w-full h-11 bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-sm rounded-[10px] transition-colors"
          >
            Acknowledge & Close
          </button>
        </div>
      </div>
    </div>
  );
}
