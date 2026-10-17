/**
 * LandIQ — lib/api.ts
 * Single source of truth for the API base URL.
 *
 * Development: VITE_API_BASE_URL may point to your local FastAPI server.
 * Production: configured in Vercel as VITE_API_BASE_URL.
 *
 * Usage:
 *   import { apiUrl } from "@/lib/api";
 *   fetch(apiUrl("/api/upload"), { method: "POST", ... })
 */

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim();
const developmentFallback = import.meta.env.DEV ? "http://127.0.0.1:8000" : undefined;

if (!configuredApiBase && !developmentFallback) {
  throw new Error("Missing VITE_API_BASE_URL. Configure the LandIQ backend URL in the deployment environment.");
}

export const API_BASE: string = (configuredApiBase || developmentFallback!).replace(/\/+$/, "");

/**
 * Builds a full API URL by appending `path` to the configured API base.
 * @param path - Must start with a slash, e.g. "/api/upload"
 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
