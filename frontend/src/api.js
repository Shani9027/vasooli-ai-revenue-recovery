import axios from 'axios'

// Resolve API base URL:
// 1. In Vite, use import.meta.env.VITE_API_URL if set.
// 2. In local dev mode (npm run dev), default to '' (leverages Vite's /api proxy to localhost:8000).
// 3. In production builds, fallback to the deployed Render backend if VITE_API_URL was not injected.
export const API_BASE = (
  import.meta.env.VITE_API_URL ||
  (import.meta.env.DEV ? '' : 'https://vasooli-backend-wu4j.onrender.com')
).replace(/\/$/, '')

// Configure axios default baseURL so all axios calls seamlessly resolve to API_BASE
axios.defaults.baseURL = API_BASE

export default API_BASE
