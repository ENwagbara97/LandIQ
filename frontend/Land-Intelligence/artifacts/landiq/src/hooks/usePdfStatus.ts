import { apiUrl } from "@/lib/api";
import { useEffect, useRef, useState } from "react";

export function usePdfStatus(reportId: string | null) {
  const [pdfReady, setPdfReady] = useState(false);
  const [pdfFailed, setPdfFailed] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | undefined>(undefined);

  useEffect(() => {
    if (!reportId) return;
    
    // Reset status when report changes
    setPdfReady(false);
    setPdfFailed(false);

    const poll = async () => {
      try {
        const r = await fetch(apiUrl(`/api/reports/${reportId}/pdf-status`));
        const d = await r.json();
        if (d.pdf_ready) {
          setPdfReady(true);
          clearInterval(pollRef.current);
        } else if (d.pdf_failed) {
          setPdfFailed(true);
          clearInterval(pollRef.current);
        }
      } catch (e) {
        console.error("Failed to poll PDF status", e);
      }
    };

    // Poll every 5 seconds
    pollRef.current = setInterval(poll, 5000);
    poll(); // check immediately

    return () => clearInterval(pollRef.current);
  }, [reportId]);

  return { pdfReady, pdfFailed };
}
