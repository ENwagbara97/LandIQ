/**
 * LandIQ — lib/api.ts
 * Single source of truth for the API base URL.
 *
 * Development (.env.local):  VITE_API_BASE_URL=http://127.0.0.1:8000
 * Production  (.env.production): VITE_API_BASE_URL=https://your-landiq-api.yourdomain.com
 *
 * Usage:
 *   import { apiUrl } from "@/lib/api";
 *   fetch(apiUrl("/api/upload"), { method: "POST", ... })
 */

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string) ?? "http://127.0.0.1:8000";

/**
 * Builds a full API URL by appending `path` to the configured API base.
 * @param path - Must start with a slash, e.g. "/api/upload"
 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
