import { MapPin, ChevronRight, Scaling, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "wouter";

const historyData = [
  { id: 1, name: "Eti-Osa LGA", score: 94, area: "1.2k sqm", date: "Oct 12", status: "green" },
  { id: 2, name: "Ikeja District", score: 78, area: "850 sqm", date: "Oct 10", status: "amber" },
  { id: 3, name: "Lekki Phase II", score: 42, area: "2.1k sqm", date: "Oct 08", status: "red" },
  { id: 4, name: "Victoria Island", score: 91, area: "450 sqm", date: "Oct 05", status: "green" }
];

export function HistoryPanel() {
  return (
    <div className="p-6 h-full flex flex-col max-w-3xl mx-auto w-full">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-1">Recent Parcels</h2>
          <p className="text-sm text-muted-foreground">Last 30 days of analysis</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-full">
          Compare (0)
        </Button>
      </div>

      <div className="space-y-4 flex-1 overflow-y-auto pb-24">
        {historyData.map((item, i) => (
          <div 
            key={item.id}
            className="group bg-card hover:bg-muted/50 border border-border rounded-2xl p-4 flex items-center gap-4 cursor-pointer transition-all duration-300 animate-in fade-in slide-in-from-bottom-4 shadow-sm hover:shadow-md"
            style={{ animationDelay: `${i * 100}ms` }}
          >
            <div className="w-12 h-12 bg-muted rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform">
              <MapPin className="w-5 h-5 text-muted-foreground" />
            </div>
            
            <div className="flex-1 min-w-0">
              <h3 className="font-bold text-foreground text-lg mb-1 truncate">{item.name}</h3>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Activity className="w-3.5 h-3.5" />
                  {item.score}/100
                </span>
                <span className="flex items-center gap-1">
                  <Scaling className="w-3.5 h-3.5" />
                  {item.area}
                </span>
                <span>{item.date}</span>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className={`w-3 h-3 rounded-full ${
                item.status === 'green' ? 'bg-[#00A294]' : 
                item.status === 'amber' ? 'bg-[#F59E0B]' : 
                'bg-[#EF4444]'
              }`} />
              <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        ))}
      </div>

      {/* FAB for Mobile */}
      <Link href="/analyse">
        <Button size="icon" className="fixed bottom-24 right-6 lg:hidden w-14 h-14 rounded-full bg-primary text-white shadow-lg hover:shadow-xl hover:-translate-y-1 transition-all z-50">
           <MapPin className="w-6 h-6" />
        </Button>
      </Link>
    </div>
  );
}
