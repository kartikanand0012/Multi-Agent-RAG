function Settings({ onClearAll }) {
  const [confirm, setConfirm] = React.useState(false);
  const services = [
    { name: 'Azure OpenAI GPT-4o', icon: 'sparkles', latency: '342ms', status: 'ok' },
    { name: 'Redis Cache', icon: 'bolt', latency: '2ms', status: 'ok' },
    { name: 'Langfuse Observability', icon: 'activity', latency: '—', status: 'ok' },
    { name: 'ChromaDB Vector Store', icon: 'layers', latency: '—', status: 'ok' },
  ];
  return (
    <div className="settings">
      <h1>System Health</h1>
      <p className="sub">Live status of services, configuration, and admin actions.</p>

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
                <div style={{width:28, height:28, borderRadius:6, background:'var(--surface-2)', display:'grid', placeItems:'center', color:'var(--text-2)'}}>
                  <Icon name={s.icon} size={14}/>
                </div>
                <span>{s.name}</span>
              </div>
              <div className={"tr-status " + s.status}>
                <span className="dot"/>
                <span style={{color:'var(--secondary)'}}>Connected</span>
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
            <div className="val">
              <span className="strong">gpt-4o</span> <span className="muted">(strong)</span>
            </div>
            <div className="val muted" style={{fontSize:12}}>fallback · gpt-4o-2 (fast)</div>
          </div>
          <div className="cfg-card">
            <div className="lbl">Embedding Model</div>
            <div className="val">text-embedding-3-large</div>
            <div className="val muted" style={{fontSize:12}}>3,072 dims · cosine</div>
          </div>
          <div className="cfg-card">
            <div className="lbl">Chunking</div>
            <div className="val">500<span className="muted"> tok</span> / 100<span className="muted"> overlap</span></div>
            <div className="val muted" style={{fontSize:12}}>recursive · structured PDFs</div>
          </div>
          <div className="cfg-card">
            <div className="lbl">Retry & Cache</div>
            <div className="val">Max 2 <span className="muted">retries</span> · 1h <span className="muted">TTL</span></div>
            <div className="val muted" style={{fontSize:12}}>Redis backend</div>
          </div>
        </div>
      </div>

      <div className="section">
        <h3 className="section-h" style={{color:'var(--danger)'}}>Danger Zone</h3>
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
          <div className="modal" style={{width:440}} onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h2 style={{color:'var(--danger)'}}>Are you absolutely sure?</h2>
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

window.Settings = Settings;
