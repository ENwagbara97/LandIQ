/**
 * LandIQ — lib/api.ts
 * Single source of truth for the API base URL.
 *
 * Set VITE_API_BASE_URL in the deployment environment to override the default.
 * Local development falls back to the local FastAPI server; production falls back
 * to the deployed Render API so a missing Vercel variable cannot silently point
 * visitors at their own computer.
 */

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim();
const defaultApiBase = import.meta.env.DEV
  ? "http://127.0.0.1:8000"
  : "https://landiq-api-oqcg.onrender.com";

export const API_BASE = (configuredApiBase || defaultApiBase).replace(/\/+$/, "");

/**
 * Builds a full API URL by appending `path` to the configured API base.
 * @param path - Must start with a slash, e.g. "/api/upload"
 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
