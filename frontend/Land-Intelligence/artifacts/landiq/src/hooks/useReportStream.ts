import { useEffect, useRef, useState, useCallback } from "react";
import { apiUrl } from "../lib/api";

const MAX_RETRIES = 15;
const RETRY_DELAY_MS = 3000; // 3s between reconnect attempts

export function useReportStream(reportId: string | null) {
  const [sections, setSections] = useState<Record<string, any>>({});
  const [stage, setStage] = useState("idle");
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const completeRef = useRef(false); // shadow of complete for onerror closure
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const checkReportFallback = useCallback(async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/api/report/${id}`));
      if (res.ok) {
        const data = await res.json();
        if (data && (data.report_id || data.run_id)) {
          setSections(data);
          completeRef.current = true;
          setComplete(true);
          setStage("complete");
          return true;
        }
      }
    } catch {
      // Fallback poll silent catch
    }
    return false;
  }, []);

  const cleanup = useCallback(() => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
  }, []);

  const connect = useCallback(() => {
    if (!reportId) return;
    cleanup();

    const streamUrl = apiUrl(`/api/reports/${reportId}/stream`);
    const es = new EventSource(streamUrl);
    esRef.current = es;

    es.addEventListener("pipeline_started", () => {
      setStage("pipeline_started");
    });

    es.addEventListener("stage_progress", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setStage(d.stage);
    });

    es.addEventListener("section_ready", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setSections(prev => ({ ...prev, [d.section]: d.data }));
    });

    es.addEventListener("report_complete", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setSections(prev => ({ ...prev, ...d }));
      completeRef.current = true;
      setComplete(true);
      setStage("complete");
      cleanup();
    });

    // Handle explicit error events emitted by the server
    es.addEventListener("error_detail", (e) => {
      try {
        const d = JSON.parse((e as MessageEvent).data);
        setErrorMessage(d.message || "Pipeline error");
      } catch {
        setErrorMessage("Pipeline error");
      }
      setError(true);
      setStage("error");
      cleanup();
    });

    // Handle SSE transport-level errors (network blip, slow external API)
    es.onerror = async () => {
      es.close();
      esRef.current = null;

      // If pipeline already completed, ignore the transport error silently
      if (completeRef.current) return;

      // Try HTTP fallback fetch first before incrementing retry count
      const isDone = await checkReportFallback(reportId);
      if (isDone) return;

      retryCountRef.current += 1;

      if (retryCountRef.current <= MAX_RETRIES) {
        // Reconnect automatically after a short delay — the pipeline is still
        // running on the backend; we just need to re-attach the SSE channel.
        setStage(`reconnecting_${retryCountRef.current}`);
        retryTimerRef.current = setTimeout(() => {
          connect();
        }, RETRY_DELAY_MS);
      } else {
        // Exhausted all retries — show the user-visible error
        setError(true);
        setStage("error");
        setErrorMessage(
          "Connection to analysis server lost after several retries. " +
          "The pipeline may still be running — please wait a moment and refresh the page."
        );
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId, cleanup, checkReportFallback]);

  useEffect(() => {
    if (!reportId) return;

    // Reset state for new report
    setSections({});
    setStage("idle");
    setComplete(false);
    setError(false);
    setErrorMessage(null);
    retryCountRef.current = 0;
    completeRef.current = false;

    connect();

    return cleanup;
  }, [reportId, connect, cleanup]);

  // Expose whether we are currently auto-reconnecting
  const reconnecting = stage.startsWith("reconnecting_");

  return { sections, stage, complete, error, errorMessage, reconnecting };
}
