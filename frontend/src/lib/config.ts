/**
 * Backend base URL, in one place so it can point at a deployed backend
 * later without touching the api layer. Override with VITE_API_BASE_URL
 * (see .env.example).
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
