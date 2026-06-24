import { MapPin, Download, FolderPlus, Info, TrendingUp, Droplets, Leaf, Mountain } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAppContext } from "@/context/AppContext";
import { cn } from "@/lib/utils";

const profileData = [
  { elevation: 120 }, { elevation: 132 }, { elevation: 145 }, 
  { elevation: 142 }, { elevation: 138 }, { elevation: 125 }, 
  { elevation: 110 }
];

export function ReportPanel() {
  const { reportData } = useAppContext();

  return (
    <div className="p-6 flex flex-col h-full animate-in fade-in slide-in-from-right-8 duration-500">
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground mb-1">
            <MapPin className="w-4 h-4" /> New South Wales, AU
          </div>
          <h2 className="text-3xl font-bold tracking-tight">Byron Shire</h2>
        </div>
        <div className="relative w-16 h-16 flex items-center justify-center">
          <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
            <path
              className="text-muted stroke-current"
              strokeWidth="3"
              fill="none"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
            <path
              className="text-[#00A294] stroke-current transition-all duration-1000 ease-out"
              strokeDasharray={`${reportData.score}, 100`}
              strokeWidth="3"
              strokeLinecap="round"
              fill="none"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
          </svg>
          <div className="absolute flex flex-col items-center justify-center text-[#00A294]">
            <span className="text-lg font-bold leading-none">{reportData.score}</span>
            <span className="text-[8px] font-bold">SCORE</span>
          </div>
        </div>
      </div>

      <div className="mb-6">
        <div className="bg-[#00A294]/10 border border-[#00A294]/20 rounded-xl p-4 flex items-center justify-center mb-4">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#00A294] animate-pulse" />
            <span className="font-bold tracking-wider text-[#00A294] uppercase text-lg">{reportData.verdict}</span>
          </div>
        </div>
        <p className="italic text-muted-foreground text-sm leading-relaxed border-l-2 border-muted pl-4">
          "{reportData.summary}"
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-2 gap-3 mb-6">
        <div className="bg-background border border-border rounded-xl p-3 shadow-sm flex flex-col">
          <Mountain className="w-5 h-5 text-muted-foreground mb-2" />
          <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Elevation</span>
          <span className="font-semibold text-sm">{reportData.metrics.elevation}</span>
        </div>
        <div className="bg-background border border-border rounded-xl p-3 shadow-sm flex flex-col">
          <TrendingUp className="w-5 h-5 text-muted-foreground mb-2" />
          <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Slope</span>
          <span className="font-semibold text-sm">{reportData.metrics.slope}</span>
        </div>
        <div className="bg-background border border-border rounded-xl p-3 shadow-sm flex flex-col">
          <Droplets className="w-5 h-5 text-blue-500 mb-2" />
          <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Flood Risk</span>
          <span className="font-semibold text-sm">{reportData.metrics.floodRisk}</span>
        </div>
        <div className="bg-background border border-border rounded-xl p-3 shadow-sm flex flex-col">
          <Leaf className="w-5 h-5 text-green-500 mb-2" />
          <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Veg Density</span>
          <span className="font-semibold text-sm">{reportData.metrics.vegDensity}</span>
        </div>
      </div>

      {/* Terrain Profile */}
      <div className="bg-background border border-border rounded-xl p-4 shadow-sm mb-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Terrain Profile</h3>
          <Badge variant="outline" className="text-[10px] font-mono">X-Section: 450m</Badge>
        </div>
        <div className="h-[80px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={profileData}>
              <defs>
                <linearGradient id="colorElevation" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0058BD" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#0058BD" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <Area 
                type="monotone" 
                dataKey="elevation" 
                stroke="#0058BD" 
                strokeWidth={2}
                fillOpacity={1} 
                fill="url(#colorElevation)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Strategic Recommendation */}
      <div className="bg-[#006A61]/5 border border-[#006A61]/20 border-l-4 border-l-[#006A61] rounded-r-xl rounded-l-sm p-4 mb-6 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <Info className="w-4 h-4 text-[#006A61]" />
          <h3 className="font-bold text-[#006A61] text-sm">Strategic Recommendation</h3>
        </div>
        <p className="text-sm text-foreground/80 leading-relaxed">
          Proceed with acquisition. Ensure standard due diligence on local zoning ordinances. Elevation profile indicates good natural drainage towards the eastern boundary.
        </p>
      </div>

      {/* Toggles & Actions */}
      <div className="mt-auto space-y-4 pt-4 border-t border-border">
        <div className="flex p-1 bg-muted rounded-full">
          <div className="flex-1 text-center py-2 px-4 rounded-full bg-background shadow-sm text-sm font-medium cursor-pointer">
            Simple Report
          </div>
          <div className="flex-1 text-center py-2 px-4 rounded-full text-muted-foreground text-sm font-medium cursor-pointer hover:text-foreground transition-colors">
            Expert Report
          </div>
        </div>
        <p className="text-xs text-center text-muted-foreground">Standard 3-page summary suitable for everyday buyers.</p>

        <div className="flex gap-3 pt-2">
          <Button variant="outline" className="flex-1 rounded-full h-12 bg-background">
            <FolderPlus className="w-4 h-4 mr-2" /> Save to Assets
          </Button>
          <Button className="flex-1 rounded-full h-12 bg-primary hover:bg-primary/90 text-white shadow-md">
            <Download className="w-4 h-4 mr-2" /> Export PDF
          </Button>
        </div>
      </div>
    </div>
  );
}
