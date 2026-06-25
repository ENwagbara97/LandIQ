import { useState } from "react";
import { Link, useLocation } from "wouter";
import {
  LayoutDashboard, FileText, Users, Bot, Map, Upload,
  BarChart2, Activity, Shield, LogOut, ChevronRight,
  TrendingUp, TrendingDown, AlertCircle, CheckCircle2,
  Clock, Zap, Globe, Database, Server, Bell, Settings,
  ExternalLink, ChevronDown, RefreshCw, Menu, X
} from "lucide-react";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from "recharts";

/* ── Mock data ─────────────────────────────────────────── */

const reportsOverTime = [
  { day: "Jun 19", reports: 142, failed: 5 },
  { day: "Jun 20", reports: 198, failed: 8 },
  { day: "Jun 21", reports: 167, failed: 4 },
  { day: "Jun 22", reports: 231, failed: 11 },
  { day: "Jun 23", reports: 289, failed: 7 },
  { day: "Jun 24", reports: 312, failed: 9 },
  { day: "Jun 25", reports: 278, failed: 6 },
];

const stateDistribution = [
  { state: "Lagos", value: 38 },
  { state: "FCT", value: 19 },
  { state: "Rivers", value: 14 },
  { state: "Ogun", value: 11 },
  { state: "Akwa Ibom", value: 8 },
  { state: "Others", value: 10 },
];

const llmDistribution = [
  { name: "GPT-4o", value: 52, color: "#0058BD" },
  { name: "Claude 3.5", value: 31, color: "#006A61" },
  { name: "Gemini Pro", value: 12, color: "#F59E0B" },
  { name: "Fallback", value: 5, color: "#EF4444" },
];

const recentReports = [
  { id: "RPT-1042", parcel: "Eti-Osa, Lagos", user: "Adewale O.", status: "completed", score: 94, time: "2 min ago" },
  { id: "RPT-1041", parcel: "Ikeja GRA, Lagos", user: "Chinonso E.", status: "processing", score: null, time: "5 min ago" },
  { id: "RPT-1040", parcel: "Maitama, FCT", user: "Fatima A.", status: "completed", score: 81, time: "12 min ago" },
  { id: "RPT-1039", parcel: "Trans-Amadi, PHC", user: "Emeka N.", status: "failed", score: null, time: "18 min ago" },
  { id: "RPT-1038", parcel: "Lekki Phase 1", user: "Olumide B.", status: "completed", score: 67, time: "24 min ago" },
  { id: "RPT-1037", parcel: "Agodi, Ibadan", user: "Taiwo K.", status: "completed", score: 88, time: "31 min ago" },
];

const apiHealth = [
  { name: "OpenAI API", status: "healthy", latency: "240ms" },
  { name: "Claude API", status: "healthy", latency: "310ms" },
  { name: "OSM Tiles", status: "healthy", latency: "45ms" },
  { name: "Cadastral DB", status: "healthy", latency: "12ms" },
  { name: "DEM Service", status: "degraded", latency: "1.8s" },
  { name: "Flood Index", status: "healthy", latency: "89ms" },
];

/* ── Sub-components ─────────────────────────────────────── */

function KpiCard({ label, value, sub, trend, color = "blue" }: {
  label: string; value: string; sub?: string; trend?: "up" | "down" | "neutral"; color?: string;
}) {
  const colors: Record<string, string> = {
    blue: "bg-[#0058BD]/8 text-[#0058BD]",
    teal: "bg-[#006A61]/8 text-[#006A61]",
    amber: "bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400",
    red: "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400",
    green: "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-500",
  };
  return (
    <div className="bg-card border border-border rounded-2xl p-5 hover:shadow-md transition-shadow">
      <p className="text-xs font-medium text-muted-foreground mb-3">{label}</p>
      <p className="text-2xl font-bold text-foreground tracking-tight">{value}</p>
      {sub && (
        <div className="flex items-center gap-1 mt-1.5">
          {trend === "up" && <TrendingUp className="w-3 h-3 text-emerald-500" />}
          {trend === "down" && <TrendingDown className="w-3 h-3 text-red-500" />}
          <p className="text-xs text-muted-foreground">{sub}</p>
        </div>
      )}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-bold text-foreground mb-4 tracking-tight">{children}</h2>;
}

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/admin" },
  { icon: FileText, label: "Reports", href: "/admin/reports" },
  { icon: Users, label: "Users", href: "/admin/users" },
  { icon: Bot, label: "AI Operations", href: "/admin/ai" },
  { icon: Map, label: "GIS Engine", href: "/admin/gis" },
  { icon: Upload, label: "Survey Plans", href: "/admin/surveys" },
  { icon: BarChart2, label: "Analytics", href: "/admin/analytics" },
  { icon: Activity, label: "System Health", href: "/admin/health" },
  { icon: Shield, label: "Admin Mgmt", href: "/admin/management" },
];

/* ── Main Component ─────────────────────────────────────── */

export function AdminPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [location] = useLocation();
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 1200);
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden font-sans">

      {/* ── Sidebar ── */}
      <aside className={`flex-shrink-0 h-full bg-[#0F1117] dark:bg-[#080A0E] flex flex-col transition-all duration-300 ease-in-out ${sidebarOpen ? "w-[220px]" : "w-[56px]"}`}>

        {/* Logo */}
        <div className="flex items-center h-14 px-4 border-b border-white/8 gap-3 flex-shrink-0">
          <div className="w-7 h-7 bg-[#0058BD] rounded-md flex items-center justify-center text-white font-bold text-xs flex-shrink-0">L</div>
          {sidebarOpen && (
            <div className="flex-1 min-w-0">
              <p className="text-white font-bold text-sm leading-none">LandIQ</p>
              <p className="text-white/30 text-[9px] tracking-wider uppercase mt-0.5">Admin Panel</p>
            </div>
          )}
          <button onClick={() => setSidebarOpen(v => !v)} className="w-6 h-6 flex items-center justify-center text-white/40 hover:text-white/80 transition-colors flex-shrink-0 ml-auto">
            {sidebarOpen ? <X className="w-3.5 h-3.5" /> : <Menu className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
          {navItems.map(({ icon: Icon, label, href }) => {
            const active = location === href;
            return (
              <Link key={href} href={href}>
                <div className={`flex items-center gap-3 px-2.5 py-2.5 rounded-xl cursor-pointer transition-all duration-150 group ${
                  active ? "bg-[#0058BD] text-white" : "text-white/50 hover:text-white hover:bg-white/6"
                }`}>
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  {sidebarOpen && <span className="text-xs font-medium truncate">{label}</span>}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="flex-shrink-0 p-3 border-t border-white/8 space-y-1">
          <Link href="/">
            <div className="flex items-center gap-3 px-2.5 py-2 rounded-xl text-white/40 hover:text-white hover:bg-white/6 cursor-pointer transition-colors">
              <ExternalLink className="w-4 h-4 flex-shrink-0" />
              {sidebarOpen && <span className="text-xs font-medium">View App</span>}
            </div>
          </Link>
          <div className="flex items-center gap-3 px-2.5 py-2 rounded-xl text-white/40 hover:text-red-400 hover:bg-red-500/10 cursor-pointer transition-colors">
            <LogOut className="w-4 h-4 flex-shrink-0" />
            {sidebarOpen && <span className="text-xs font-medium">Sign Out</span>}
          </div>
          {sidebarOpen && (
            <div className="flex items-center gap-2 px-2.5 pt-3">
              <div className="w-6 h-6 rounded-full bg-[#0058BD]/40 flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0">A</div>
              <div className="min-w-0 flex-1">
                <p className="text-white/80 text-[11px] font-medium truncate">Admin User</p>
                <p className="text-white/30 text-[9px] truncate">admin@landiq.ng</p>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">

        {/* Top bar */}
        <div className="flex-shrink-0 h-14 bg-card border-b border-border flex items-center justify-between px-6">
          <div>
            <p className="text-xs text-muted-foreground">Admin <ChevronRight className="inline w-3 h-3" /> Dashboard</p>
            <h1 className="text-sm font-bold text-foreground leading-none mt-0.5">System Performance Hub</h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleRefresh} className={`w-8 h-8 rounded-full bg-muted hover:bg-muted/80 flex items-center justify-center text-muted-foreground transition-colors ${refreshing ? "animate-spin" : ""}`}>
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button className="w-8 h-8 rounded-full bg-muted hover:bg-muted/80 flex items-center justify-center text-muted-foreground transition-colors">
              <Bell className="w-3.5 h-3.5" />
            </button>
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold">A</div>
          </div>
        </div>

        {/* Dashboard body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
            <KpiCard label="Total Users" value="12,451" sub="+4.2% this week" trend="up" color="blue" />
            <KpiCard label="Active Today" value="1,321" sub="vs 1,183 yesterday" trend="up" color="teal" />
            <KpiCard label="Reports Generated" value="5,832" sub="All time" color="blue" />
            <KpiCard label="Success Rate" value="97.8%" sub="-0.3% from last week" trend="down" color="green" />
            <KpiCard label="Failed Reports" value="127" sub="+11 today" trend="down" color="red" />
            <KpiCard label="Monthly Revenue" value="₦4.3M" sub="+18% MoM" trend="up" color="teal" />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

            {/* Report volume chart */}
            <div className="xl:col-span-2 bg-card border border-border rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <SectionTitle>Report Volume</SectionTitle>
                  <p className="text-xs text-muted-foreground -mt-3">Last 7 days · daily breakdown</p>
                </div>
                <div className="flex gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[#0058BD]" />Generated</span>
                  <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-400" />Failed</span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={reportsOverTime}>
                  <defs>
                    <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#0058BD" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#0058BD" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="redGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#EF4444" stopOpacity={0.12} />
                      <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid #e5e7eb', boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
                  <Area type="monotone" dataKey="reports" stroke="#0058BD" strokeWidth={2} fill="url(#blueGrad)" dot={false} />
                  <Area type="monotone" dataKey="failed" stroke="#EF4444" strokeWidth={1.5} fill="url(#redGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* LLM distribution */}
            <div className="bg-card border border-border rounded-2xl p-5">
              <SectionTitle>AI Model Usage</SectionTitle>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={llmDistribution} cx="50%" cy="50%" innerRadius={50} outerRadius={72} paddingAngle={3} dataKey="value">
                    {llmDistribution.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 10, fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 mt-2">
                {llmDistribution.map(d => (
                  <div key={d.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: d.color }} />
                      <span className="text-xs text-muted-foreground">{d.name}</span>
                    </div>
                    <span className="text-xs font-semibold text-foreground">{d.value}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Middle row */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

            {/* Recent reports table */}
            <div className="xl:col-span-2 bg-card border border-border rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <p className="text-sm font-bold text-foreground">Recent Reports</p>
                <button className="text-xs text-primary font-medium hover:underline flex items-center gap-1">
                  View all <ChevronRight className="w-3 h-3" />
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      {["Report ID", "Parcel", "User", "Score", "Status", "Time"].map(h => (
                        <th key={h} className="text-left px-5 py-3 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {recentReports.map((r, i) => (
                      <tr key={r.id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                        <td className="px-5 py-3 text-xs font-mono text-muted-foreground">{r.id}</td>
                        <td className="px-5 py-3 text-xs font-medium text-foreground">{r.parcel}</td>
                        <td className="px-5 py-3 text-xs text-muted-foreground">{r.user}</td>
                        <td className="px-5 py-3 text-xs font-bold text-foreground">{r.score ?? "—"}</td>
                        <td className="px-5 py-3">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                            r.status === "completed" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" :
                            r.status === "processing" ? "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400" :
                            "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          }`}>
                            {r.status === "completed" && <CheckCircle2 className="w-2.5 h-2.5" />}
                            {r.status === "processing" && <Clock className="w-2.5 h-2.5" />}
                            {r.status === "failed" && <AlertCircle className="w-2.5 h-2.5" />}
                            {r.status.charAt(0).toUpperCase() + r.status.slice(1)}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-xs text-muted-foreground">{r.time}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Nigeria state distribution */}
            <div className="bg-card border border-border rounded-2xl p-5">
              <SectionTitle>Reports by State</SectionTitle>
              <div className="space-y-3">
                {stateDistribution.map(s => (
                  <div key={s.state}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-muted-foreground">{s.state}</span>
                      <span className="font-semibold text-foreground">{s.value}%</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-[#0058BD]"
                        style={{ width: `${s.value}%`, opacity: 0.7 + (s.value / 100) * 0.3 }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Bottom row — AI ops + System health */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

            {/* AI Operations */}
            <div className="bg-card border border-border rounded-2xl p-5">
              <SectionTitle>AI Operations</SectionTitle>
              <div className="grid grid-cols-2 gap-3 mb-4">
                {[
                  { label: "Agent Success Rate", value: "96.4%", icon: <Zap className="w-3.5 h-3.5 text-[#0058BD]" /> },
                  { label: "Avg Response Time", value: "2.8s", icon: <Clock className="w-3.5 h-3.5 text-[#006A61]" /> },
                  { label: "Fallback Rate", value: "11.3%", icon: <AlertCircle className="w-3.5 h-3.5 text-amber-500" /> },
                  { label: "Tokens Today", value: "4.2M", icon: <Activity className="w-3.5 h-3.5 text-purple-500" /> },
                ].map(m => (
                  <div key={m.label} className="bg-muted/40 rounded-xl p-3 flex items-start gap-2.5">
                    <div className="mt-0.5">{m.icon}</div>
                    <div>
                      <p className="text-[10px] text-muted-foreground leading-tight">{m.label}</p>
                      <p className="text-base font-bold text-foreground mt-0.5">{m.value}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">LLM Cost Today</p>
                {[
                  { name: "OpenAI", cost: "$23.40", pct: 56 },
                  { name: "Claude", cost: "$18.10", pct: 43 },
                  { name: "Gemini", cost: "$4.50", pct: 11 },
                ].map(c => (
                  <div key={c.name} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-14">{c.name}</span>
                    <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-[#0058BD] rounded-full" style={{ width: `${c.pct}%` }} />
                    </div>
                    <span className="text-xs font-semibold text-foreground w-12 text-right">{c.cost}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* System Health */}
            <div className="bg-card border border-border rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <SectionTitle>System Health</SectionTitle>
                <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  5 of 6 Operational
                </span>
              </div>
              <div className="space-y-2.5">
                {apiHealth.map(s => (
                  <div key={s.name} className="flex items-center justify-between py-2 border-b border-border/40 last:border-0">
                    <div className="flex items-center gap-2.5">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.status === "healthy" ? "bg-emerald-500" : "bg-amber-400 animate-pulse"}`} />
                      <span className="text-xs font-medium text-foreground">{s.name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] font-mono text-muted-foreground">{s.latency}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${
                        s.status === "healthy"
                          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400"
                          : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
                      }`}>
                        {s.status === "healthy" ? "OK" : "DEGRADED"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* GIS Metrics */}
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">GIS Engine Metrics</p>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { label: "Flood Analysis", value: "3.2s" },
                    { label: "Slope Analysis", value: "1.1s" },
                    { label: "Map Generation", value: "2.4s" },
                  ].map(m => (
                    <div key={m.label} className="bg-muted/40 rounded-lg p-2.5 text-center">
                      <p className="text-sm font-bold text-foreground">{m.value}</p>
                      <p className="text-[9px] text-muted-foreground leading-tight mt-0.5">{m.label}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
