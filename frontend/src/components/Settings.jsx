import React, { useEffect, useState } from 'react';
import { fetchHealth } from '../services/api';

function StatusRow({ label, ok, latency }) {
  return (
    <div className="status-row">
      <span className={`status-dot ${ok ? 'ok' : 'err'}`}/>
      <span className="status-label">{label}</span>
      <span className="status-right">{ok ? 'Connected' : 'Unavailable'}{latency ? ` · ${latency}` : ''}</span>
    </div>
  );
}

export default function Settings({ onClearAll }) {
  const [health, setHealth] = useState(null);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="settings-page">
      <h2 className="settings-heading">System Health &amp; Settings</h2>

      <div className="settings-section">
        <div className="section-title">API Connection Status</div>
        {health ? (
          <div className="status-table">
            <StatusRow label="Azure OpenAI" ok={true}/>
            <StatusRow label="Redis Cache" ok={health.redis}/>
            <StatusRow label="ChromaDB" ok={true} latency={`${health.chromadb_collections} collections`}/>
            <StatusRow label="Langfuse Observability" ok={health.langfuse}/>
          </div>
        ) : (
          <div className="status-loading">Checking system status…</div>
        )}
      </div>

      <div className="settings-section">
        <div className="section-title">Current Configuration</div>
        <div className="config-grid">
          {[
            ['Strong model', 'gpt-4o (80k TPM)'],
            ['Fast model', 'gpt-4o-2 (20k TPM)'],
            ['Embedding', 'text-embedding-3-large (3072 dims)'],
            ['Chunk size', '500 tokens · overlap 100'],
            ['Max retries', '2 · Cache TTL 1h'],
            ['Indexing', 'RAPTOR hierarchical'],
          ].map(([k, v]) => (
            <div key={k} className="config-item">
              <span className="config-key">{k}</span>
              <span className="config-val">{v}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="settings-section danger-zone">
        <div className="section-title danger-title">Danger Zone</div>
        {!confirm ? (
          <button className="btn-danger" onClick={() => setConfirm(true)}>
            Clear all notebooks
          </button>
        ) : (
          <div className="confirm-row">
            <span>Are you sure? This cannot be undone.</span>
            <button className="btn-danger" onClick={() => { onClearAll(); setConfirm(false); }}>
              Yes, clear everything
            </button>
            <button className="btn-ghost" onClick={() => setConfirm(false)}>Cancel</button>
          </div>
        )}
      </div>
    </div>
  );
}
