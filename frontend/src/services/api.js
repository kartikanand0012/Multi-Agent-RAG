import { apiClient, tokenStore } from './auth';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

// ── Health (public) ────────────────────────────────────────────────────────────
export const fetchHealth = () => apiClient.get('/health').then(r => r.data);

// ── Upload ────────────────────────────────────────────────────────────────────
export const uploadFile = (file, notebookId, useRaptor = true) => {
  const form = new FormData();
  form.append('file', file);
  form.append('notebook_id', notebookId);
  form.append('use_raptor', String(useRaptor));
  return apiClient.post('/upload', form).then(r => r.data);
};

// ── Streaming query — returns AbortController ─────────────────────────────────
export const streamQuery = (query, notebookId, callbacks = {}) => {
  const ctrl = new AbortController();
  const { onIntent, onRetrieval, onToken, onValidation, onDone, onError } = callbacks;

  const token = tokenStore.get();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, notebook_id: notebookId }),
    signal: ctrl.signal,
  }).then(async res => {
    if (!res.ok) { onError?.(`HTTP ${res.status}`); return; }
    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if      (event.type === 'intent')     onIntent?.(event);
          else if (event.type === 'retrieval')  onRetrieval?.(event);
          else if (event.type === 'token')      onToken?.(event.content);
          else if (event.type === 'validation') onValidation?.(event);
          else if (event.type === 'done')       onDone?.();
          else if (event.type === 'error')      onError?.(event.message);
          else if (event.type === 'warning')    onValidation?.({ ...event, warning: true });
        } catch {}
      }
    }
  }).catch(err => {
    if (err.name !== 'AbortError') onError?.(err.message);
  });

  return ctrl;
};

// ── Notebooks (CRUD) ──────────────────────────────────────────────────────────
export const fetchNotebooks    = ()           => apiClient.get('/notebooks').then(r => r.data);
export const createNotebook    = (id, name)   => apiClient.post('/notebooks', { id, name }).then(r => r.data);
export const renameNotebook    = (id, name)   => apiClient.patch(`/notebooks/${id}`, { name }).then(r => r.data);
export const deleteNotebook    = (id)         => apiClient.delete(`/notebooks/${id}`);

// ── Notebook data ─────────────────────────────────────────────────────────────
export const fetchStats = id  => apiClient.get(`/notebook/${id}/stats`).then(r => r.data);
export const fetchMap   = id  => apiClient.get(`/notebook/${id}/map`).then(r => r.data);
