// Runtime API base URL resolution.
//
// The deployed frontend (Vercel) must talk to a backend whose URL is only
// known at deploy time. import.meta.env.VITE_API_URL is baked in at *build*
// time, so we layer runtime overrides on top — no rebuild needed when the
// backend moves.
//
// Precedence:
//   1. `?api=<url>` query param  (also persists to localStorage)
//   2. localStorage 'rag_api_url' (set from the Settings page)
//   3. window.__RAG_API_URL__     (inline script / edge injection)
//   4. import.meta.env.VITE_API_URL (build-time)
//   5. http://localhost:8000/api/v1 (local dev fallback)

const KEY = 'rag_api_url';
const DEFAULT = 'http://localhost:8000/api/v1';

function normalize(url) {
  return String(url || '').trim().replace(/\/+$/, '');
}

export function getStoredApiUrl() {
  try {
    return normalize(localStorage.getItem(KEY)) || '';
  } catch {
    return '';
  }
}

export function setStoredApiUrl(url) {
  const clean = normalize(url);
  try {
    if (clean) localStorage.setItem(KEY, clean);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable — ignore */
  }
  return clean;
}

export function resolveApiBase() {
  if (typeof window !== 'undefined') {
    try {
      const qp = new URLSearchParams(window.location.search).get('api');
      if (qp && normalize(qp)) return setStoredApiUrl(qp);
    } catch {
      /* ignore malformed query strings */
    }
    const stored = getStoredApiUrl();
    if (stored) return stored;
    if (window.__RAG_API_URL__ && normalize(window.__RAG_API_URL__)) {
      return normalize(window.__RAG_API_URL__);
    }
  }
  const buildTime =
    typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_URL;
  return normalize(buildTime) || DEFAULT;
}
