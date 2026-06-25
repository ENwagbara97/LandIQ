import { useState } from "react";
import { Download, FolderPlus, Info, TrendingUp, Droplets, Leaf, Mountain, MapPin } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAppContext } from "@/context/AppContext";
import { cn } from "@/lib/utils";

const profileData = [
  { d: "0m", elevation: 120 },
  { d: "75m", elevation: 132 },
  { d: "150m", elevation: 145 },
  { d: "225m", elevation: 142 },
  { d: "300m", elevation: 138 },
  { d: "375m", elevation: 125 },
  { d: "450m", elevation: 110 },
];

const metrics = [
  { icon: Mountain, label: "Elevation", color: "text-slate-500", key: "elevation" },
  { icon: TrendingUp, label: "Slope", color: "text-blue-500", key: "slope" },
  { icon: Droplets, label: "Flood Risk", color: "text-sky-500", key: "floodRisk" },
  { icon: Leaf, label: "Veg Density", color: "text-emerald-500", key: "vegDensity" },
];

export function ReportPanel() {
  const { reportData } = useAppContext();
  const [reportType, setReportType] = useState<"simple" | "expert">("simple");

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-5 pt-5 pb-4 space-y-5">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1">
              <MapPin className="w-3.5 h-3.5" /> Lagos State, Nigeria
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-foreground leading-tight">
              Boundary Analysis
            </h2>
          </div>
          {/* Score ring */}
          <div className="relative w-14 h-14 flex-shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
              <path
                className="stroke-muted"
                strokeWidth="3.5"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                stroke="#00A294"
                strokeDasharray={`${reportData.score}, 100`}
                strokeWidth="3.5"
                strokeLinecap="round"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                style={{ transition: "stroke-dasharray 1s ease" }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center text-[#00A294]">
              <span className="text-base font-bold leading-none">{reportData.score}</span>
              <span className="text-[7px] font-bold tracking-wide">SCORE</span>
            </div>
          </div>
        </div>

        {/* Verdict banner */}
        <div className="bg-[#00A294]/10 border border-[#00A294]/20 rounded-2xl px-4 py-3 flex items-center gap-3">
          <span className="w-2.5 h-2.5 rounded-full bg-[#00A294] animate-pulse flex-shrink-0" />
          <span className="font-bold tracking-wider text-[#00A294] uppercase text-sm">{reportData.verdict}</span>
        </div>

        {/* Summary */}
        <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-muted pl-3 italic">
          "{reportData.summary}"
        </p>

        {/* Metrics grid — icon + label + value together */}
        <div className="grid grid-cols-2 gap-2.5">
          {metrics.map(({ icon: Icon, label, color, key }) => (
            <div key={key} className="bg-muted/40 border border-border/60 rounded-2xl p-3.5 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Icon className={cn("w-4 h-4", color)} />
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">{label}</span>
              </div>
              <span className="font-semibold text-sm text-foreground">
                {reportData.metrics[key as keyof typeof reportData.metrics]}
              </span>
            </div>
          ))}
        </div>

        {/* Terrain Profile */}
        <div className="bg-muted/30 border border-border/60 rounded-2xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Terrain Profile</span>
            <Badge variant="outline" className="text-[10px] font-mono h-5">X-Section: 450m</Badge>
          </div>
          <div className="h-[90px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={profileData} margin={{ top: 4, right: 0, bottom: 0, left: -24 }}>
                <defs>
                  <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0058BD" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#0058BD" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="d" tick={{ fontSize: 9, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ borderRadius: 10, fontSize: 11, border: "1px solid #e5e7eb" }}
                  formatter={(v) => [`${v}m`, "Elevation"]}
                />
                <Area
                  type="monotone"
                  dataKey="elevation"
                  stroke="#0058BD"
                  strokeWidth={2}
                  fill="url(#elevGrad)"
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Strategic Recommendation */}
        <div className="rounded-2xl rounded-l-sm border-l-4 border-l-[#006A61] border border-[#006A61]/20 bg-[#006A61]/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Info className="w-4 h-4 text-[#006A61] flex-shrink-0" />
            <h3 className="font-bold text-[#006A61] text-sm">Strategic Recommendation</h3>
          </div>
          <p className="text-sm text-foreground/80 leading-relaxed">
            Proceed with acquisition. Ensure standard due diligence on local zoning ordinances.
            Elevation profile indicates good natural drainage towards the eastern boundary.
          </p>
        </div>
      </div>

      {/* Sticky footer with report type toggle + actions */}
      <div className="flex-shrink-0 px-5 pt-4 pb-5 border-t border-border space-y-3 bg-card/80 backdrop-blur-sm">
        {/* Report type toggle */}
        <div className="flex p-1 bg-muted rounded-full gap-1">
          {(["simple", "expert"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setReportType(t)}
              className={cn(
                "flex-1 py-2 px-3 rounded-full text-xs font-semibold transition-all duration-200",
                reportType === t
                  ? "bg-white dark:bg-card shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t === "simple" ? "Simple Report" : "Expert Report"}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-center text-muted-foreground">
          {reportType === "simple"
            ? "Standard 3-page summary suitable for everyday buyers."
            : "Full technical report with GIS data, 14+ pages."}
        </p>

        {/* Action buttons */}
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1 rounded-full h-11 text-sm" size="sm">
            <FolderPlus className="w-3.5 h-3.5 mr-1.5" /> Save to Assets
          </Button>
          <Button className="flex-1 rounded-full h-11 bg-primary hover:bg-primary/90 text-white shadow-md text-sm" size="sm">
            <Download className="w-3.5 h-3.5 mr-1.5" /> Export PDF
          </Button>
        </div>
      </div>
    </div>
  );
}
