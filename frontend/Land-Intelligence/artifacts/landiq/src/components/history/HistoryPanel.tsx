import { MapPin, ChevronRight, Scaling, Activity, Plus, Search, Loader2, ArrowLeft, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link, useLocation } from "wouter";
import { useState, useEffect } from "react";
import { useAppContext } from "@/context/AppContext";
import { useMobile } from "@/hooks/use-mobile";
import { apiUrl } from "@/lib/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const statusColor: Record<string, string> = { GREEN: "bg-[#00A294]", AMBER: "bg-amber-400", RED: "bg-red-500", UNKNOWN: "bg-gray-400" };
const statusLabel: Record<string, string> = { GREEN: "Low Risk", AMBER: "Moderate", RED: "High Risk", UNKNOWN: "Unknown" };

interface HistoryItem {
  report_id: string;
  generated_at: string;
  parcel_state: string | null;
  parcel_lga: string | null;
  traffic_light: string | null;
  overall_risk_score: number | null;
  report_json: any;
}

export function HistoryPanel() {
  const [search, setSearch] = useState("");
  const [historyData, setHistoryData] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const { setSessionId, setAnalysisState } = useAppContext();
  const [, setLocation] = useLocation();
  const isMobile = useMobile();

  useEffect(() => {
    async function fetchHistory() {
      try {
        const res = await fetch(apiUrl("/api/history"));
        if (res.ok) {
          const data = await res.json();
          setHistoryData(data);
        }
      } catch (err) {
        console.error("Failed to fetch history:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchHistory();
  }, []);

  const filtered = historyData.filter(h =>
    (h.parcel_lga || "").toLowerCase().includes(search.toLowerCase()) ||
    (h.parcel_state || "").toLowerCase().includes(search.toLowerCase())
  );

  const openReport = (report_id: string) => {
    setSessionId(report_id);
    setAnalysisState("complete");
    setLocation("/report");
  };

  const handleDeleteAll = async () => {
    try {
      const res = await fetch(apiUrl("/api/history"), { method: "DELETE" });
      if (res.ok) {
        setHistoryData([]);
      }
    } catch (err) {
      console.error("Failed to delete all history", err);
    }
  };

  const handleDeleteItem = async (e: React.MouseEvent, report_id: string) => {
    e.stopPropagation();
    try {
      const res = await fetch(apiUrl(`/api/history/${report_id}`), { method: "DELETE" });
      if (res.ok) {
        setHistoryData(prev => prev.filter(h => h.report_id !== report_id));
      }
    } catch (err) {
      console.error("Failed to delete item", err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex-shrink-0">
        <div className="flex items-start justify-between mb-4 gap-2">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            {/* Back button — visible on all devices now */}
            <button
              onClick={() => setLocation("/")}
              className="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0 active:scale-95 transition-transform hover:bg-muted/80"
              aria-label="Back to dashboard"
            >
              <ArrowLeft className="w-4 h-4 text-foreground" />
            </button>
            <div className="min-w-0">
              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground truncate">Recent Parcels</h2>
              <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5 truncate">Last 30 days of analysis</p>
            </div>
          </div>
          
          {historyData.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-600 hover:bg-red-500/10 px-2 sm:px-3 flex-shrink-0">
                  <Trash2 className="w-3.5 h-3.5 sm:w-4 sm:h-4 mr-1.5" />
                  <span className="text-[10px] sm:text-sm">Delete All</span>
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete all history?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete all your previously generated parcel reports. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDeleteAll} className="bg-red-500 hover:bg-red-600 text-white">
                    Yes, delete all
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search parcels..."
            className="w-full pl-8 pr-4 py-2 text-xs bg-muted/50 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 placeholder-muted-foreground"
          />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-5 pb-32 space-y-2.5">
        {loading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">No parcels found</div>
        ) : (
          filtered.map((item, i) => {
            let rep: any = {};
            try {
              rep = typeof item.report_json === 'string' ? JSON.parse(item.report_json) : (item.report_json || {});
            } catch (e) {
              rep = {};
            }
            const statusStr = item.traffic_light || rep.summary?.traffic_light || "UNKNOWN";
            const dt = item.generated_at ? new Date(item.generated_at).toLocaleDateString() : "Unknown date";
            const areaHa = rep.parcel_geometry?.computed_area_ha || (rep.parcel_geometry?.area_sqm ? rep.parcel_geometry.area_sqm / 10000 : null);
            const area = areaHa
              ? `${(areaHa * 10000).toLocaleString(undefined, { maximumFractionDigits: 0 })} sqm`
              : "Unknown Area";
            const locCtx = rep.parcel_geometry?.location_context || {};
            const locationTitle = (item as any).location_display || locCtx.display_location || (item.parcel_lga ? `${item.parcel_lga}, ${item.parcel_state || 'Nigeria'}` : (item.parcel_state || "Nigerian Parcel"));
            const score = item.overall_risk_score !== null ? item.overall_risk_score : (rep.summary?.overall_risk_score ?? null);

            return (
              <div
                key={item.report_id}
                onClick={() => openReport(item.report_id)}
                className={`group relative bg-card border rounded-2xl p-4 flex items-center gap-3 cursor-pointer transition-all duration-200 shadow-sm hover:shadow-md active:scale-[0.99] border-border hover:border-border/80 hover:bg-muted/30`}
                style={{ animationDelay: `${i * 60}ms` }}
              >
                {/* Icon */}
                <div className="w-11 h-11 bg-muted rounded-xl flex items-center justify-center flex-shrink-0">
                  <MapPin className="w-4.5 h-4.5 text-muted-foreground" style={{ width: 18, height: 18 }} />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0 pr-2">
                  <h3 className="font-semibold text-foreground text-sm truncate">{locationTitle}</h3>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mt-1.5 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Activity className="w-3 h-3 flex-shrink-0" />
                      {score !== null ? `${score}/100` : "N/A"}
                    </span>
                    <span className="flex items-center gap-1">
                      <Scaling className="w-3 h-3 flex-shrink-0" />
                      {area}
                    </span>
                    <span className="text-muted-foreground/80 flex-shrink-0">{dt}</span>
                  </div>
                </div>

                {/* Status + chevron + delete */}
                <div className="flex flex-col items-end justify-between flex-shrink-0 h-full py-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${statusColor[statusStr] || statusColor.UNKNOWN}`} />
                    <span className="text-[10px] font-medium text-muted-foreground">
                      {statusLabel[statusStr] || statusLabel.UNKNOWN}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-auto pt-2">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button 
                          onClick={(e) => e.stopPropagation()}
                          className="p-1.5 text-muted-foreground/40 hover:text-red-500 hover:bg-red-500/10 rounded-md transition-colors"
                          title="Delete report"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete this report?</AlertDialogTitle>
                          <AlertDialogDescription>
                            Are you sure you want to delete this parcel analysis?
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel onClick={(e) => e.stopPropagation()}>Cancel</AlertDialogCancel>
                          <AlertDialogAction 
                            onClick={(e) => { e.stopPropagation(); handleDeleteItem(e, item.report_id); }}
                            className="bg-red-500 hover:bg-red-600 text-white"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/40 group-hover:text-muted-foreground group-hover:translate-x-0.5 transition-all" />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* FAB — Plus icon, fixed above bottom nav */}
      <Link href="/analyse">
        <button className="fixed bottom-[88px] right-5 lg:hidden w-14 h-14 rounded-full bg-primary text-white shadow-lg hover:shadow-xl active:scale-95 transition-all z-[90] flex items-center justify-center">
          <Plus className="w-6 h-6" />
        </button>
      </Link>
    </div>
  );
}
