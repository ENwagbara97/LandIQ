import { MapPin, ChevronRight, Scaling, Activity, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "wouter";
import { useState } from "react";

const historyData = [
  { id: 1, name: "Eti-Osa LGA", location: "Lagos State", score: 94, area: "1,200 sqm", date: "Oct 12", status: "green" },
  { id: 2, name: "Ikeja District", location: "Lagos State", score: 78, area: "850 sqm", date: "Oct 10", status: "amber" },
  { id: 3, name: "Lekki Phase II", location: "Lagos State", score: 42, area: "2,100 sqm", date: "Oct 08", status: "red" },
  { id: 4, name: "Victoria Island", location: "Lagos State", score: 91, area: "450 sqm", date: "Oct 05", status: "green" },
];

const statusColor = { green: "bg-[#00A294]", amber: "bg-amber-400", red: "bg-red-500" };
const statusLabel = { green: "Low Risk", amber: "Moderate", red: "High Risk" };

export function HistoryPanel() {
  const [selected, setSelected] = useState<number[]>([]);
  const [search, setSearch] = useState("");

  const toggle = (id: number) =>
    setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  const filtered = historyData.filter(h =>
    h.name.toLowerCase().includes(search.toLowerCase()) ||
    h.location.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex-shrink-0">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-foreground">Recent Parcels</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Last 30 days of analysis</p>
          </div>
          {selected.length > 0 && (
            <Button variant="outline" size="sm" className="rounded-full text-xs h-8 border-primary/30 text-primary">
              Compare ({selected.length})
            </Button>
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
      <div className="flex-1 overflow-y-auto px-5 pb-24 space-y-2.5">
        {filtered.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No parcels found</div>
        )}
        {filtered.map((item, i) => {
          const isSelected = selected.includes(item.id);
          return (
            <div
              key={item.id}
              onClick={() => toggle(item.id)}
              className={`group relative bg-card border rounded-2xl p-4 flex items-center gap-3 cursor-pointer transition-all duration-200 shadow-sm hover:shadow-md active:scale-[0.99] ${
                isSelected
                  ? "border-primary/40 bg-primary/5 dark:bg-primary/10"
                  : "border-border hover:border-border/80 hover:bg-muted/30"
              }`}
              style={{ animationDelay: `${i * 60}ms` }}
            >
              {/* Selection indicator */}
              {isSelected && (
                <span className="absolute top-3 right-3 w-4 h-4 rounded-full bg-primary flex items-center justify-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-white" />
                </span>
              )}

              {/* Icon */}
              <div className="w-11 h-11 bg-muted rounded-xl flex items-center justify-center flex-shrink-0">
                <MapPin className="w-4.5 h-4.5 text-muted-foreground" style={{ width: 18, height: 18 }} />
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-foreground text-sm truncate">{item.name}</h3>
                <p className="text-[11px] text-muted-foreground truncate">{item.location}</p>
                <div className="flex items-center gap-3 mt-1.5 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Activity className="w-3 h-3" />
                    {item.score}/100
                  </span>
                  <span className="flex items-center gap-1">
                    <Scaling className="w-3 h-3" />
                    {item.area}
                  </span>
                  <span>{item.date}</span>
                </div>
              </div>

              {/* Status + chevron */}
              <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${statusColor[item.status as keyof typeof statusColor]}`} />
                  <span className="text-[10px] font-medium text-muted-foreground">
                    {statusLabel[item.status as keyof typeof statusLabel]}
                  </span>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/40 group-hover:text-muted-foreground group-hover:translate-x-0.5 transition-all" />
              </div>
            </div>
          );
        })}
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
