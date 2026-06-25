import { useState } from "react";
import { Link } from "wouter";
import {
  LayoutDashboard, FileText, Users, Bot, Map, Upload,
  BarChart2, Activity, Shield, LogOut, ChevronRight,
  TrendingUp, TrendingDown, AlertCircle, CheckCircle2,
  Clock, Zap, Globe, RefreshCw, Menu, X, ExternalLink, Bell,
  Search, Filter, Download, Eye, MoreHorizontal, UserCheck,
  UserX, Building2, Cpu, Database, Server, Wifi, AlertTriangle
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from "recharts";

/* ── Mock Data ── */
const reportVolume = [
  { day: "Jun 19", reports: 142, failed: 5 }, { day: "Jun 20", reports: 198, failed: 8 },
  { day: "Jun 21", reports: 167, failed: 4 }, { day: "Jun 22", reports: 231, failed: 11 },
  { day: "Jun 23", reports: 289, failed: 7 }, { day: "Jun 24", reports: 312, failed: 9 },
  { day: "Jun 25", reports: 278, failed: 6 },
];
const stateData = [
  { state: "Lagos", value: 38 }, { state: "FCT", value: 19 }, { state: "Rivers", value: 16 },
  { state: "Ogun", value: 11 }, { state: "Akwa Ibom", value: 8 }, { state: "Enugu", value: 5 }, { state: "Others", value: 3 },
];
const llmDist = [
  { name: "GPT-4o", value: 52, color: "#0058BD" },
  { name: "Claude 3.5", value: 31, color: "#006A61" },
  { name: "Gemini Pro", value: 12, color: "#F59E0B" },
  { name: "Fallback", value: 5, color: "#EF4444" },
];
const recentReports = [
  { id: "RPT-1042", parcel: "Eti-Osa, Lagos", user: "Adewale O.", score: 94, status: "completed", time: "2 min ago" },
  { id: "RPT-1041", parcel: "Ikeja GRA, Lagos", user: "Chinonso E.", score: null, status: "processing", time: "5 min ago" },
  { id: "RPT-1040", parcel: "Maitama, FCT", user: "Fatima A.", score: 81, status: "completed", time: "12 min ago" },
  { id: "RPT-1039", parcel: "Trans-Amadi, PHC", user: "Emeka N.", score: null, status: "failed", time: "18 min ago" },
  { id: "RPT-1038", parcel: "Lekki Phase 1", user: "Olumide B.", score: 67, status: "completed", time: "24 min ago" },
  { id: "RPT-1037", parcel: "Agodi, Ibadan", user: "Taiwo K.", score: 88, status: "completed", time: "31 min ago" },
  { id: "RPT-1036", parcel: "Maitama South, FCT", user: "Fatima A.", score: 77, status: "completed", time: "45 min ago" },
  { id: "RPT-1035", parcel: "Festac Town, Lagos", user: "Bola M.", score: null, status: "failed", time: "1 hr ago" },
];
const users = [
  { name: "Adewale Okafor", email: "adewale@gmail.com", plan: "Pro", reports: 34, status: "active", joined: "Mar 2026" },
  { name: "Chinonso Eze", email: "chinonso@law.ng", plan: "Enterprise", reports: 127, status: "active", joined: "Jan 2026" },
  { name: "Fatima Aliyu", email: "fatima@estate.ng", plan: "Free", reports: 3, status: "active", joined: "Jun 2026" },
  { name: "Emeka Nwosu", email: "emeka@nwosu.com", plan: "Pro", reports: 18, status: "suspended", joined: "Feb 2026" },
  { name: "Olumide Balogun", email: "olumide@vent.ng", plan: "Pro", reports: 42, status: "active", joined: "Apr 2026" },
  { name: "Taiwo Kehinde", email: "taiwo@citydev.ng", plan: "Enterprise", reports: 89, status: "active", joined: "Jan 2026" },
  { name: "Bola Martins", email: "bola@estate.ng", plan: "Free", reports: 1, status: "inactive", joined: "Jun 2026" },
];
const apiHealth = [
  { name: "OpenAI API", status: "healthy", latency: "240ms" },
  { name: "Claude API", status: "healthy", latency: "310ms" },
  { name: "OSM Tiles", status: "healthy", latency: "45ms" },
  { name: "Cadastral DB", status: "healthy", latency: "12ms" },
  { name: "DEM Service", status: "degraded", latency: "1.8s" },
  { name: "Flood Index", status: "healthy", latency: "89ms" },
];
const surveyPlans = [
  { id: "SP-001", file: "Lekki_Survey_2024.pdf", uploader: "Olumide B.", size: "2.4 MB", ocr: 96, status: "extracted", date: "Jun 25" },
  { id: "SP-002", file: "Ikeja_GRA_Plan.zip", uploader: "Chinonso E.", size: "5.1 MB", ocr: 89, status: "extracted", date: "Jun 25" },
  { id: "SP-003", file: "Maitama_Boundary.pdf", uploader: "Fatima A.", size: "1.8 MB", ocr: null, status: "failed", date: "Jun 24" },
  { id: "SP-004", file: "Trans-Amadi_Survey.pdf", uploader: "Emeka N.", size: "3.2 MB", ocr: 94, status: "review", date: "Jun 24" },
  { id: "SP-005", file: "Agodi_Estate_2023.pdf", uploader: "Taiwo K.", size: "4.7 MB", ocr: 91, status: "extracted", date: "Jun 23" },
];
const weeklyUsers = [
  { week: "W1", new: 42, active: 380 }, { week: "W2", new: 58, active: 412 },
  { week: "W3", new: 71, active: 445 }, { week: "W4", new: 63, active: 430 },
];

type Section = "dashboard" | "reports" | "users" | "ai" | "gis" | "surveys" | "analytics" | "health" | "management";

const navItems: { id: Section; icon: React.ElementType; label: string }[] = [
  { id: "dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { id: "reports", icon: FileText, label: "Reports" },
  { id: "users", icon: Users, label: "Users" },
  { id: "ai", icon: Bot, label: "AI Operations" },
  { id: "gis", icon: Map, label: "GIS Engine" },
  { id: "surveys", icon: Upload, label: "Survey Plans" },
  { id: "analytics", icon: BarChart2, label: "Analytics" },
  { id: "health", icon: Activity, label: "System Health" },
  { id: "management", icon: Shield, label: "Admin Mgmt" },
];

/* ── Sub-components ── */
function KpiCard({ label, value, sub, trend }: { label: string; value: string; sub?: string; trend?: "up" | "down" }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4 hover:shadow-sm transition-shadow">
      <p className="text-xs text-muted-foreground mb-2">{label}</p>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {sub && (
        <div className="flex items-center gap-1 mt-1">
          {trend === "up" && <TrendingUp className="w-3 h-3 text-emerald-500" />}
          {trend === "down" && <TrendingDown className="w-3 h-3 text-red-500" />}
          <p className="text-xs text-muted-foreground">{sub}</p>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    processing: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    failed: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    active: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    suspended: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    inactive: "bg-muted text-muted-foreground",
    extracted: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    review: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
    healthy: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    degraded: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
  };
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${map[status] ?? "bg-muted text-muted-foreground"}`}>
      {status}
    </span>
  );
}

/* ── Section Views ── */
function DashboardView() {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <KpiCard label="Total Users" value="12,451" sub="+4.2% this week" trend="up" />
        <KpiCard label="Active Today" value="1,321" sub="vs 1,183 yesterday" trend="up" />
        <KpiCard label="Reports Generated" value="5,832" sub="All time" />
        <KpiCard label="Success Rate" value="97.8%" sub="-0.3% from last week" trend="down" />
        <KpiCard label="Failed Reports" value="127" sub="+11 today" trend="down" />
        <KpiCard label="Monthly Revenue" value="₦4.3M" sub="+18% MoM" trend="up" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-card border border-border rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-bold text-foreground">Report Volume</p>
              <p className="text-xs text-muted-foreground">Last 7 days</p>
            </div>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[#0058BD]" />Generated</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-400" />Failed</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={reportVolume}>
              <defs>
                <linearGradient id="bg1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0058BD" stopOpacity={0.15} /><stop offset="95%" stopColor="#0058BD" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.04)" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 10, fontSize: 11 }} />
              <Area type="monotone" dataKey="reports" stroke="#0058BD" strokeWidth={2} fill="url(#bg1)" dot={false} />
              <Area type="monotone" dataKey="failed" stroke="#EF4444" strokeWidth={1.5} fill="none" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold text-foreground mb-4">AI Model Usage</p>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart><Pie data={llmDist} cx="50%" cy="50%" innerRadius={48} outerRadius={68} paddingAngle={3} dataKey="value">
              {llmDist.map((e, i) => <Cell key={i} fill={e.color} />)}
            </Pie><Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 8, fontSize: 11 }} /></PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">{llmDist.map(d => (
            <div key={d.name} className="flex items-center justify-between">
              <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ background: d.color }} /><span className="text-xs text-muted-foreground">{d.name}</span></div>
              <span className="text-xs font-semibold">{d.value}%</span>
            </div>
          ))}</div>
        </div>
      </div>
      <div className="grid xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-card border border-border rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
            <p className="text-sm font-bold">Recent Reports</p>
            <button className="text-xs text-primary font-medium flex items-center gap-1 hover:underline">View all <ChevronRight className="w-3 h-3" /></button>
          </div>
          <ReportsTable rows={recentReports.slice(0, 5)} />
        </div>
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-4">Reports by State</p>
          {stateData.map(s => (
            <div key={s.state} className="mb-2.5">
              <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{s.state}</span><span className="font-semibold">{s.value}%</span></div>
              <div className="h-1.5 bg-muted rounded-full"><div className="h-full bg-[#0058BD] rounded-full" style={{ width: `${s.value}%`, opacity: 0.6 + s.value / 100 * 0.4 }} /></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReportsTable({ rows }: { rows: typeof recentReports }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          {["Report ID", "Parcel", "User", "Score", "Status", "Time"].map(h => (
            <th key={h} className="text-left px-4 py-3 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className="border-b border-border/40 hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{r.id}</td>
              <td className="px-4 py-3 text-xs font-medium">{r.parcel}</td>
              <td className="px-4 py-3 text-xs text-muted-foreground">{r.user}</td>
              <td className="px-4 py-3 text-xs font-bold">{r.score ?? "—"}</td>
              <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
              <td className="px-4 py-3 text-xs text-muted-foreground">{r.time}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportsView() {
  const [filter, setFilter] = useState("all");
  const filtered = recentReports.filter(r => filter === "all" ? true : r.status === filter);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><p className="text-lg font-bold">All Reports</p><p className="text-xs text-muted-foreground">5,832 total · 127 failed</p></div>
        <div className="flex gap-2">
          <button className="flex items-center gap-1.5 text-xs border border-border px-3 h-8 rounded-full hover:bg-muted"><Filter className="w-3 h-3" />Filter</button>
          <button className="flex items-center gap-1.5 text-xs bg-primary text-white px-3 h-8 rounded-full hover:bg-primary/90"><Download className="w-3 h-3" />Export</button>
        </div>
      </div>
      <div className="flex gap-2 text-xs">
        {["all", "completed", "processing", "failed"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-full capitalize transition-colors ${filter === f ? "bg-primary text-white" : "bg-muted text-muted-foreground hover:bg-muted/80"}`}>
            {f}
          </button>
        ))}
      </div>
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <ReportsTable rows={filtered} />
      </div>
    </div>
  );
}

function UsersView() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><p className="text-lg font-bold">Users</p><p className="text-xs text-muted-foreground">12,451 registered</p></div>
        <button className="flex items-center gap-1.5 text-xs bg-primary text-white px-3 h-8 rounded-full"><Download className="w-3 h-3" />Export</button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="Total Users" value="12,451" sub="+4.2% this week" trend="up" />
        <KpiCard label="Pro/Enterprise" value="2,840" sub="22.8% of users" />
        <KpiCard label="Churned (30d)" value="143" sub="-12% vs last month" trend="up" />
      </div>
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border flex items-center gap-3">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input placeholder="Search users..." className="flex-1 text-sm bg-transparent outline-none placeholder-muted-foreground" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr className="border-b border-border">
              {["User", "Plan", "Reports", "Status", "Joined", "Actions"].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={i} className="border-b border-border/40 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary flex-shrink-0">
                        {u.name.charAt(0)}
                      </div>
                      <div>
                        <p className="text-xs font-medium">{u.name}</p>
                        <p className="text-[10px] text-muted-foreground">{u.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3"><span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${u.plan === "Enterprise" ? "bg-[#0058BD]/10 text-[#0058BD]" : u.plan === "Pro" ? "bg-[#006A61]/10 text-[#006A61]" : "bg-muted text-muted-foreground"}`}>{u.plan}</span></td>
                  <td className="px-4 py-3 text-xs font-bold text-foreground">{u.reports}</td>
                  <td className="px-4 py-3"><StatusBadge status={u.status} /></td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{u.joined}</td>
                  <td className="px-4 py-3"><button className="p-1 hover:bg-muted rounded-lg transition-colors"><MoreHorizontal className="w-4 h-4 text-muted-foreground" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AIView() {
  return (
    <div className="space-y-5">
      <div><p className="text-lg font-bold">AI Operations</p><p className="text-xs text-muted-foreground">Real-time model monitoring</p></div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Agent Success Rate" value="96.4%" sub="+0.2% today" trend="up" />
        <KpiCard label="Avg Response Time" value="2.8s" sub="-0.4s from yesterday" trend="up" />
        <KpiCard label="Fallback Rate" value="11.3%" sub="+1.1% this week" trend="down" />
        <KpiCard label="Tokens Today" value="4.2M" />
      </div>
      <div className="grid xl:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-1">LLM Distribution</p>
          <p className="text-xs text-muted-foreground mb-4">Today's model usage split</p>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart><Pie data={llmDist} cx="50%" cy="50%" innerRadius={60} outerRadius={85} paddingAngle={3} dataKey="value">
              {llmDist.map((e, i) => <Cell key={i} fill={e.color} />)}
            </Pie><Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 8, fontSize: 11 }} /></PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-2 gap-2 mt-2">{llmDist.map(d => (
            <div key={d.name} className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: d.color }} /><div><p className="text-xs text-muted-foreground">{d.name}</p><p className="text-xs font-bold">{d.value}%</p></div></div>
          ))}</div>
        </div>
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-4">LLM Cost Today</p>
          {[{ name: "OpenAI", cost: "$23.40", pct: 56 }, { name: "Claude", cost: "$18.10", pct: 43 }, { name: "Gemini", cost: "$4.50", pct: 11 }].map(c => (
            <div key={c.name} className="mb-4">
              <div className="flex justify-between text-xs mb-1.5"><span className="font-medium">{c.name}</span><span className="font-bold text-foreground">{c.cost}</span></div>
              <div className="h-2 bg-muted rounded-full"><div className="h-full bg-[#0058BD] rounded-full" style={{ width: `${c.pct}%` }} /></div>
            </div>
          ))}
          <div className="mt-6 pt-4 border-t border-border">
            <p className="text-xs text-muted-foreground mb-3 font-semibold">Common Failure Types</p>
            {[["Parse Failure", "34"], ["Prompt Failure", "22"], ["Hallucination", "18"], ["Invalid Response", "12"]].map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs py-1.5 border-b border-border/40 last:border-0"><span className="text-muted-foreground">{k}</span><span className="font-semibold">{v}</span></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function GISView() {
  return (
    <div className="space-y-5">
      <div><p className="text-lg font-bold">GIS Engine</p><p className="text-xs text-muted-foreground">Spatial analysis monitoring</p></div>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {[
          { label: "Flood Analysis Avg", value: "3.2s" }, { label: "Slope Analysis Avg", value: "1.1s" },
          { label: "Map Generation Avg", value: "2.4s" }, { label: "DEM Failures", value: "34" },
          { label: "Invalid Coords", value: "82" }, { label: "Failed Spatial Ops", value: "17" },
        ].map(m => <KpiCard key={m.label} label={m.label} value={m.value} />)}
      </div>
      <div className="grid xl:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-4">Spatial Analysis Queue</p>
          {[
            { task: "Flood Risk — Lekki Phase 5", status: "processing", elapsed: "1.2s" },
            { task: "DEM Processing — FCT Plot 44A", status: "processing", elapsed: "3.8s" },
            { task: "Slope Analysis — Ikeja GRA", status: "completed", elapsed: "0.9s" },
            { task: "Map Generation — Rivers", status: "completed", elapsed: "2.1s" },
            { task: "Coord Validation — Ogun", status: "failed", elapsed: "—" },
          ].map((t, i) => (
            <div key={i} className="flex items-center justify-between py-2.5 border-b border-border/40 last:border-0">
              <div className="flex items-center gap-2.5 min-w-0"><div className={`w-2 h-2 rounded-full flex-shrink-0 ${t.status === "processing" ? "bg-blue-500 animate-pulse" : t.status === "completed" ? "bg-emerald-500" : "bg-red-500"}`} /><span className="text-xs truncate">{t.task}</span></div>
              <div className="flex items-center gap-3 flex-shrink-0 ml-2"><span className="text-[10px] text-muted-foreground font-mono">{t.elapsed}</span><StatusBadge status={t.status} /></div>
            </div>
          ))}
        </div>
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-4">Survey Error Analysis</p>
          {[["Missing Coordinates", "38%"], ["Wrong CRS", "21%"], ["Corrupt PDF", "18%"], ["Unreadable Scan", "14%"], ["Missing Bearings", "9%"]].map(([k, v]) => (
            <div key={k} className="mb-3">
              <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{k}</span><span className="font-semibold">{v}</span></div>
              <div className="h-1.5 bg-muted rounded-full"><div className="h-full bg-amber-400 rounded-full" style={{ width: v }} /></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SurveysView() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><p className="text-lg font-bold">Survey Plans</p><p className="text-xs text-muted-foreground">Uploaded documents & extraction logs</p></div>
        <div className="flex gap-2 text-xs">
          <span className="text-emerald-600 font-semibold">Upload: 98.2%</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-[#0058BD] font-semibold">OCR: 93%</span>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="Total Uploaded" value="1,247" sub="All time" />
        <KpiCard label="Pending Review" value="41" sub="Manual check needed" trend="down" />
        <KpiCard label="Extraction Success" value="96%" sub="+1.2% this month" trend="up" />
      </div>
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr className="border-b border-border">
              {["Plan ID", "File", "Uploader", "Size", "OCR Acc.", "Status", "Date"].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {surveyPlans.map(s => (
                <tr key={s.id} className="border-b border-border/40 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{s.id}</td>
                  <td className="px-4 py-3 text-xs font-medium">{s.file}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{s.uploader}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{s.size}</td>
                  <td className="px-4 py-3 text-xs font-bold">{s.ocr ? `${s.ocr}%` : "—"}</td>
                  <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{s.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AnalyticsView() {
  return (
    <div className="space-y-5">
      <div><p className="text-lg font-bold">Analytics</p><p className="text-xs text-muted-foreground">Usage, revenue & geographic insights</p></div>
      <div className="grid xl:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-1">Weekly User Growth</p>
          <p className="text-xs text-muted-foreground mb-4">New vs active users</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weeklyUsers}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.04)" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 10, fontSize: 11 }} />
              <Bar dataKey="new" fill="#0058BD" radius={[4, 4, 0, 0]} name="New Users" />
              <Bar dataKey="active" fill="#006A61" radius={[4, 4, 0, 0]} name="Active Users" fillOpacity={0.3} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-card border border-border rounded-2xl p-5">
          <p className="text-sm font-bold mb-4">Nigeria — Reports by State</p>
          {stateData.map(s => (
            <div key={s.state} className="mb-2.5">
              <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{s.state}</span><span className="font-semibold">{s.value}%</span></div>
              <div className="h-1.5 bg-muted rounded-full"><div className="h-full bg-[#0058BD] rounded-full" style={{ width: `${s.value}%`, opacity: 0.6 + s.value / 100 * 0.4 }} /></div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid xl:grid-cols-3 gap-3">
        <KpiCard label="Conversion Rate" value="14.2%" sub="Free → Paid" trend="up" />
        <KpiCard label="Avg Revenue / User" value="₦8,450" sub="Monthly" trend="up" />
        <KpiCard label="Churn Rate" value="2.3%" sub="-0.5% from last month" trend="up" />
      </div>
    </div>
  );
}

function HealthView() {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div><p className="text-lg font-bold">System Health</p><p className="text-xs text-muted-foreground">Service status & performance</p></div>
        <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 dark:bg-emerald-900/20 px-2.5 py-1 rounded-full flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />5 of 6 Operational</span>
      </div>
      <div className="bg-card border border-border rounded-2xl divide-y divide-border">
        {apiHealth.map(s => (
          <div key={s.name} className="flex items-center justify-between px-5 py-4">
            <div className="flex items-center gap-3">
              <span className={`w-2.5 h-2.5 rounded-full ${s.status === "healthy" ? "bg-emerald-500" : "bg-amber-400 animate-pulse"}`} />
              <div>
                <p className="text-sm font-medium">{s.name}</p>
                <p className="text-[10px] text-muted-foreground">{s.status === "degraded" ? "Response time elevated" : "All systems normal"}</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs font-mono text-muted-foreground">{s.latency}</span>
              <StatusBadge status={s.status} />
            </div>
          </div>
        ))}
      </div>
      <div className="grid xl:grid-cols-3 gap-3">
        {[{ label: "Flood Analysis Avg", value: "3.2s", icon: Zap }, { label: "Slope Analysis Avg", value: "1.1s", icon: TrendingUp }, { label: "Map Generation Avg", value: "2.4s", icon: Globe }].map(m => (
          <div key={m.label} className="bg-card border border-border rounded-2xl p-4 flex items-center gap-3">
            <m.icon className="w-5 h-5 text-[#0058BD]" />
            <div><p className="text-xs text-muted-foreground">{m.label}</p><p className="text-xl font-bold">{m.value}</p></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ManagementView() {
  const roles = [
    { name: "Super Admin", users: 2, perms: "Full access" },
    { name: "Operations", users: 5, perms: "Reports, Users, GIS" },
    { name: "Support", users: 12, perms: "Users, Reports (read)" },
    { name: "Analyst", users: 8, perms: "Analytics, Reports (read)" },
  ];
  return (
    <div className="space-y-5">
      <div><p className="text-lg font-bold">Admin Management</p><p className="text-xs text-muted-foreground">Role & access control</p></div>
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border flex items-center justify-between">
          <p className="text-sm font-bold">Admin Roles</p>
          <button className="text-xs bg-primary text-white px-3 h-7 rounded-full hover:bg-primary/90">+ Add Role</button>
        </div>
        <div className="divide-y divide-border">
          {roles.map(r => (
            <div key={r.name} className="flex items-center justify-between px-5 py-4">
              <div><p className="text-sm font-medium">{r.name}</p><p className="text-xs text-muted-foreground">{r.perms}</p></div>
              <div className="flex items-center gap-4">
                <span className="text-xs font-semibold text-muted-foreground">{r.users} users</span>
                <button className="p-1 hover:bg-muted rounded-lg transition-colors"><MoreHorizontal className="w-4 h-4 text-muted-foreground" /></button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Main Admin Page ── */
export function AdminPage() {
  const [section, setSection] = useState<Section>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const sectionTitles: Record<Section, string> = {
    dashboard: "System Performance Hub", reports: "All Reports", users: "User Management",
    ai: "AI Operations", gis: "GIS Engine", surveys: "Survey Plans",
    analytics: "Usage Analytics", health: "System Health", management: "Admin Management",
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside className={`flex-shrink-0 h-full bg-[#0F1117] dark:bg-[#080A0E] flex flex-col transition-all duration-300 ${sidebarOpen ? "w-[220px]" : "w-[56px]"}`}>
        <div className="flex items-center h-14 px-4 border-b border-white/8 gap-3 flex-shrink-0">
          <div className="w-7 h-7 bg-[#0058BD] rounded-md flex items-center justify-center text-white font-bold text-xs flex-shrink-0">L</div>
          {sidebarOpen && <div className="flex-1 min-w-0"><p className="text-white font-bold text-sm leading-none">LandIQ</p><p className="text-white/30 text-[9px] tracking-wider uppercase mt-0.5">Admin Panel</p></div>}
          <button onClick={() => setSidebarOpen(v => !v)} className="w-6 h-6 flex items-center justify-center text-white/40 hover:text-white/80 transition-colors flex-shrink-0 ml-auto">
            {sidebarOpen ? <X className="w-3.5 h-3.5" /> : <Menu className="w-3.5 h-3.5" />}
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
          {navItems.map(({ id, icon: Icon, label }) => (
            <button key={id} onClick={() => setSection(id)}
              className={`w-full flex items-center gap-3 px-2.5 py-2.5 rounded-xl transition-all duration-150 ${section === id ? "bg-[#0058BD] text-white" : "text-white/50 hover:text-white hover:bg-white/6"}`}>
              <Icon className="w-4 h-4 flex-shrink-0" />
              {sidebarOpen && <span className="text-xs font-medium truncate">{label}</span>}
            </button>
          ))}
        </nav>
        <div className="flex-shrink-0 p-3 border-t border-white/8 space-y-1">
          <Link href="/"><div className="flex items-center gap-3 px-2.5 py-2 rounded-xl text-white/40 hover:text-white hover:bg-white/6 cursor-pointer transition-colors"><ExternalLink className="w-4 h-4 flex-shrink-0" />{sidebarOpen && <span className="text-xs font-medium">View App</span>}</div></Link>
          <div className="flex items-center gap-3 px-2.5 py-2 rounded-xl text-white/40 hover:text-red-400 hover:bg-red-500/10 cursor-pointer transition-colors"><LogOut className="w-4 h-4 flex-shrink-0" />{sidebarOpen && <span className="text-xs font-medium">Sign Out</span>}</div>
          {sidebarOpen && <div className="flex items-center gap-2 px-2.5 pt-3"><div className="w-6 h-6 rounded-full bg-[#0058BD]/40 flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0">A</div><div className="min-w-0"><p className="text-white/80 text-[11px] font-medium truncate">Admin User</p><p className="text-white/30 text-[9px] truncate">admin@landiq.ng</p></div></div>}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-shrink-0 h-14 bg-card border-b border-border flex items-center justify-between px-6">
          <div>
            <p className="text-xs text-muted-foreground">Admin <ChevronRight className="inline w-3 h-3" /> {navItems.find(n => n.id === section)?.label}</p>
            <h1 className="text-sm font-bold text-foreground leading-none mt-0.5">{sectionTitles[section]}</h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => { setRefreshing(true); setTimeout(() => setRefreshing(false), 1200); }}
              className={`w-8 h-8 rounded-full bg-muted hover:bg-muted/80 flex items-center justify-center text-muted-foreground transition-colors ${refreshing ? "animate-spin" : ""}`}>
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button className="w-8 h-8 rounded-full bg-muted hover:bg-muted/80 flex items-center justify-center text-muted-foreground"><Bell className="w-3.5 h-3.5" /></button>
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold">A</div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {section === "dashboard" && <DashboardView />}
          {section === "reports" && <ReportsView />}
          {section === "users" && <UsersView />}
          {section === "ai" && <AIView />}
          {section === "gis" && <GISView />}
          {section === "surveys" && <SurveysView />}
          {section === "analytics" && <AnalyticsView />}
          {section === "health" && <HealthView />}
          {section === "management" && <ManagementView />}
        </div>
      </div>
    </div>
  );
}
