import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const client = axios.create({ baseURL: BASE, timeout: 120000 });

// ── Health ────────────────────────────────────────────────────────────────────
export const fetchHealth = () => client.get('/health').then(r => r.data);

// ── Upload ────────────────────────────────────────────────────────────────────
export const uploadFile = (file, notebookId, useRaptor = true) => {
  const form = new FormData();
  form.append('file', file);
  form.append('notebook_id', notebookId);
  form.append('use_raptor', String(useRaptor));
  return client.post('/upload', form).then(r => r.data);
};

// ── Query (non-streaming) ─────────────────────────────────────────────────────
export const queryNotebook = (query, notebookId) =>
  client.post('/query', { query, notebook_id: notebookId }).then(r => r.data);

// ── Streaming query — returns an AbortController, calls callbacks per event ──
export const streamQuery = (query, notebookId, callbacks = {}) => {
  const ctrl = new AbortController();
  const { onIntent, onRetrieval, onToken, onValidation, onDone, onError } = callbacks;

  fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, notebook_id: notebookId }),
    signal: ctrl.signal,
  }).then(async res => {
    if (!res.ok) {
      onError?.(`HTTP ${res.status}`);
      return;
    }
    const reader = res.body.getReader();
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
          if (event.type === 'intent')      onIntent?.(event);
          else if (event.type === 'retrieval') onRetrieval?.(event);
          else if (event.type === 'token')  onToken?.(event.content);
          else if (event.type === 'validation') onValidation?.(event);
          else if (event.type === 'done')   onDone?.();
          else if (event.type === 'error')  onError?.(event.message);
          else if (event.type === 'warning') onValidation?.({ ...event, warning: true });
        } catch {}
      }
    }
  }).catch(err => {
    if (err.name !== 'AbortError') onError?.(err.message);
  });

  return ctrl;
};

// ── Notebook ──────────────────────────────────────────────────────────────────
export const fetchStats   = id => client.get(`/notebook/${id}/stats`).then(r => r.data);
export const fetchMap     = id => client.get(`/notebook/${id}/map`).then(r => r.data);
export const deleteNotebook = id => client.delete(`/notebook/${id}`).then(r => r.data);
