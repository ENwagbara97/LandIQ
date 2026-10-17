import React, { useEffect, useState } from "react";
import { 
  Newspaper, 
  ExternalLink, 
  ShieldCheck, 
  AlertTriangle, 
  Waves, 
  Flame, 
  Landmark, 
  FileWarning, 
  ChevronDown, 
  ChevronUp 
} from "lucide-react";
import { apiUrl } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

interface NewsAlert {
  id: number;
  event_type: string;
  lga: string;
  state: string;
  source_quote: string;
  date_mentioned?: string;
  confidence: string;
  corroboration_count: number;
  status: "CONFIRMED" | "PENDING" | "AUDIT" | "DISMISSED";
  created_at: string;
  newspaper?: string;
  article_url?: string;
  article_title?: string;
  article_date?: string;
}

interface NewsAlertsWidgetProps {
  lga?: string | null;
  state?: string | null;
}

export function NewsAlertsWidget({ lga, state }: NewsAlertsWidgetProps) {
  const [alerts, setAlerts] = useState<NewsAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!lga && !state) {
      setAlerts([]);
      setLoading(false);
      return;
    }

    let isMounted = true;
    setLoading(true);

    const queryParams = new URLSearchParams();
    if (lga) {
      queryParams.set("lga", lga);
      queryParams.set("exact", "true");
    }
    if (state) queryParams.set("state", state);
    queryParams.set("days", "180"); // 6 months context

    fetch(apiUrl(`/api/news/alerts?${queryParams.toString()}`))
      .then((res) => (res.ok ? res.json() : []))
      .then((data: NewsAlert[]) => {
        if (isMounted) {
          setAlerts(data || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.warn("[NewsAlertsWidget] Failed to fetch news alerts:", err);
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [lga, state]);

  if (!lga && !state) {
    return (
      <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4">
        <div className="flex items-center gap-2 pb-2 border-b border-[var(--report-border)]">
          <Newspaper className="w-4 h-4 text-indigo-500" />
          <h3 className="text-xs font-bold text-[var(--report-muted)] uppercase tracking-wider">
            News-to-Risk Intelligence
          </h3>
        </div>
        <div className="mt-3 text-xs text-[var(--report-muted)]">
          Select or load a report to see location-specific news and risk alerts.
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4 animate-pulse">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-4 h-4 bg-slate-300 dark:bg-slate-700 rounded-full" />
          <div className="w-40 h-3 bg-slate-300 dark:bg-slate-700 rounded" />
        </div>
        <div className="w-full h-8 bg-slate-200 dark:bg-slate-800 rounded mt-2" />
      </div>
    );
  }

  const confirmedAlerts = alerts.filter((a) => a.status === "CONFIRMED");
  const pendingAlerts = alerts.filter((a) => a.status === "PENDING");
  const totalCount = confirmedAlerts.length + pendingAlerts.length;

  const getEventIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case "flood":
        return <Waves className="w-4 h-4 text-sky-500" />;
      case "fire":
        return <Flame className="w-4 h-4 text-rose-500" />;
      case "demolition":
        return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case "land_dispute":
        return <Landmark className="w-4 h-4 text-purple-500" />;
      case "cof_revocation":
        return <FileWarning className="w-4 h-4 text-red-500" />;
      default:
        return <Newspaper className="w-4 h-4 text-slate-400" />;
    }
  };

  const getEventBadge = (type: string) => {
    const formatted = type.replace("_", " ").toUpperCase();
    switch (type.toLowerCase()) {
      case "flood":
        return <Badge className="bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20">{formatted}</Badge>;
      case "demolition":
        return <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20">{formatted}</Badge>;
      case "land_dispute":
        return <Badge className="bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20">{formatted}</Badge>;
      case "cof_revocation":
        return <Badge className="bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20">{formatted}</Badge>;
      default:
        return <Badge variant="outline">{formatted}</Badge>;
    }
  };

  return (
    <div className="rounded-[10px] border border-[var(--report-border)] bg-[var(--report-surface)] p-4 mb-4">
      <div className="flex items-center justify-between pb-2 border-b border-[var(--report-border)]">
        <div className="flex items-center gap-2">
          <Newspaper className="w-4 h-4 text-indigo-500" />
          <h3 className="text-xs font-bold text-[var(--report-muted)] uppercase tracking-wider">
            News-to-Risk Intelligence ({lga || state || "Local Area"})
          </h3>
        </div>
        {totalCount > 0 && (
          <Badge
            variant={confirmedAlerts.length > 0 ? "destructive" : "secondary"}
            className="text-[10px] px-2 py-0.5 font-bold uppercase tracking-wider"
          >
            {confirmedAlerts.length > 0 ? `${confirmedAlerts.length} Confirmed Risk(s)` : `${pendingAlerts.length} Signal(s)`}
          </Badge>
        )}
      </div>

      {totalCount === 0 ? (
        <div className="mt-3 flex items-start gap-2 text-xs text-[var(--report-secondary)]">
          <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">Zero active dispute/flood headlines detected</span> in official newspaper monitoring for {lga || "this area"} over the last 180 days.
          </div>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-[var(--report-secondary)]">
            Groundsource pipeline parsed and verified the following risk mentions in regional press:
          </p>

          {(expanded ? alerts : alerts.slice(0, 2)).map((alert) => (
            <div
              key={alert.id}
              className="p-3 rounded-lg border border-[var(--report-border)] bg-slate-50/50 dark:bg-slate-900/50 flex flex-col gap-2"
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-1.5">
                  {getEventIcon(alert.event_type)}
                  {getEventBadge(alert.event_type)}
                  {alert.status === "CONFIRMED" ? (
                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-0.5">
                      <ShieldCheck className="w-3 h-3" /> Corroborated ({alert.corroboration_count} sources)
                    </span>
                  ) : (
                    <span className="text-[10px] text-amber-600 dark:text-amber-400 font-medium">
                      Single source (Corroboration pending)
                    </span>
                  )}
                </div>
                {alert.newspaper && (
                  <span className="text-[11px] font-medium text-[var(--report-muted)]">
                    {alert.newspaper} {(alert.article_date || alert.date_mentioned) ? ` • ${alert.article_date || alert.date_mentioned}` : ""}
                  </span>
                )}
              </div>

              <blockquote className="text-xs italic text-[var(--report-foreground)] border-l-2 border-indigo-400 pl-2.5 my-1">
                "{alert.source_quote}"
              </blockquote>

              <div className="flex items-center justify-between text-[11px] text-[var(--report-muted)] pt-1 border-t border-[var(--report-border)]/50">
                <span>Location: <strong>{alert.lga ? `${alert.lga}, ${alert.state}` : alert.state}</strong></span>
                {alert.article_url && (
                  <a
                    href={alert.article_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-indigo-500 hover:text-indigo-600 font-medium transition-colors"
                  >
                    Source article <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          ))}

          {alerts.length > 2 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs font-semibold text-indigo-500 hover:text-indigo-600 flex items-center gap-1 mt-2"
            >
              {expanded ? (
                <>Show less <ChevronUp className="w-3.5 h-3.5" /></>
              ) : (
                <>View all {alerts.length} verified news signals <ChevronDown className="w-3.5 h-3.5" /></>
              )}
            </button>
          )}
        </div>
      )}

      <div className="mt-3 pt-2 border-t border-[var(--report-border)] text-[10px] text-[var(--report-muted)] flex items-center justify-between">
        <span>Scanned via Gemini 6-Layer Verification</span>
        <span>Updated Daily (02:00 WAT)</span>
      </div>
    </div>
  );
}
