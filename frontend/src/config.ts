// The one place the backend URL is set. Override with VITE_API_URL in frontend/.env.
export const API_URL: string = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

export const POLL_ACTIVE_MS = 1500 // while a run is going
export const POLL_IDLE_MS = 6000 // otherwise
