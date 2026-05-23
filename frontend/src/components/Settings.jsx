import React, { useEffect, useState } from 'react';
import Icon from './Icons';
import { fetchHealth, fetchVersion } from '../services/api';

export default function Settings({ onClearAll }) {
  const [confirm, setConfirm] = useState(false);
  const [health, setHealth]   = useState(null);
  const [version, setVersion] = useState(null);

  useEffect(() => {
    const t0 = Date.now();
    fetchHealth()
      .then(d => setHealth({ ...d, _ms: Date.now() - t0 }))
      .catch(() => setHealth(null));
    fetchVersion().then(setVersion).catch(() => setVersion(null));
  }, []);

  const services = [
    { name: 'FastAPI Backend',        icon: 'sparkles',  latency: health ? `${health._ms}ms`                        : '—', status: health    ? 'ok'  : 'pending' },
    { name: 'Redis Cache',            icon: 'bolt',      latency: health?.redis   ? 'connected'                     : '—', status: health?.redis   ? 'ok'  : 'err'     },
    { name: 'Langfuse Observability', icon: 'activity',  latency: health?.langfuse ? 'tracing on'                   : '—', status: health?.langfuse ? 'ok'  : 'err'     },
    { name: 'ChromaDB Vector Store',  icon: 'layers',    latency: health ? `${health.chromadb_collections} collection${health.chromadb_collections !== 1 ? 's' : ''}` : '—', status: 'ok' },
  ];

  return (
    <div className="settings">
      <h1>System Health</h1>
      <p className="sub">Live status of services, configuration, and admin actions.</p>

      {version && (
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 18, padding: '10px 14px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>
          <span>Live build</span>
          <code style={{ color: 'var(--text)' }}>{version.commit}</code>
          <span className="muted">·</span>
          <span>{version.environment}</span>
        </div>
      )}

      <div className="section">
        <h3 className="section-h">API Connection Status</h3>
        <div className="table-card">
          <div className="table-row head">
            <div>Service</div>
            <div>Status</div>
            <div>Latency</div>
          </div>
          {services.map(s => (
            <div key={s.name} className="table-row">
              <div className="tr-svc">
                <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--surface-2)', display: 'grid', placeItems: 'center', color: 'var(--text-2)' }}>
                  <Icon name={s.icon} size={14}/>
                </div>
                <span>{s.name}</span>
              </div>
              <div className={"tr-status " + s.status}>
                <span className="dot"/>
                <span style={{ color: s.status === 'ok' ? 'var(--secondary)' : 'var(--danger)' }}>
                  {s.status === 'ok' ? 'Connected' : s.status === 'pending' ? 'Checking…' : 'Unavailable'}
                </span>
              </div>
              <div className="tr-latency">{s.latency}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3 className="section-h">Model Configuration</h3>
        <div className="cfg-grid">
          <div className="cfg-card">
            <div className="lbl">Reasoning Model</div>
            <div className="val"><span className="strong">gpt-4o</span> <span className="muted">(strong)</span></div>
            <div className="val muted" style={{ fontSize: 12 }}>fallback · gpt-4o-2 (fast)</div>
          </div>
          <div className="cfg-card">
            <div className="lbl">Embedding Model</div>
            <div className="val">text-embedding-3-large</div>
            <div className="val muted" style={{ fontSize: 12 }}>3,072 dims · cosine</div>
          </div>
          <div className="cfg-card">
            <div className="lbl">Chunking</div>
            <div className="val">500<span className="muted"> tok</span> / 100<span className="muted"> overlap</span></div>
            <div className="val muted" style={{ fontSize: 12 }}>recursive · structured PDFs</div>
          </div>
          <div className="cfg-card">
            <div className="lbl">Retry &amp; Cache</div>
            <div className="val">Max 2 <span className="muted">retries</span> · 1h <span className="muted">TTL</span></div>
            <div className="val muted" style={{ fontSize: 12 }}>Redis backend</div>
          </div>
        </div>
      </div>

      <div className="section">
        <h3 className="section-h" style={{ color: 'var(--danger)' }}>Danger Zone</h3>
        <div className="danger-card">
          <div className="di">
            <b>Clear all notebooks</b>
            <p>Permanently deletes every notebook, indexed document, and cached response. This cannot be undone.</p>
          </div>
          <button className="btn-danger" onClick={() => setConfirm(true)}>Clear all data</button>
        </div>
      </div>

      {confirm && (
        <div className="modal-overlay" onClick={() => setConfirm(false)}>
          <div className="modal" style={{ width: 440 }} onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h2 style={{ color: 'var(--danger)' }}>Are you absolutely sure?</h2>
              <button className="icon-btn" onClick={() => setConfirm(false)}><Icon name="x" size={16}/></button>
            </div>
            <div className="modal-body">
              <div className="confirm-body">
                This will permanently delete <b>all notebooks</b>, <b>all indexed documents</b>,
                and clear the RAPTOR tree from ChromaDB. The cache will be flushed.
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn-ghost" onClick={() => setConfirm(false)}>Cancel</button>
              <button className="btn-danger" onClick={() => { onClearAll(); setConfirm(false); }}>
                Yes, delete everything
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
