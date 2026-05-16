function StatsTab({ stats }) {
  const layers = stats.layerBreakdown; // { l2, l1, l0 }
  const total = layers.l2 + layers.l1 + layers.l0;
  return (
    <div className="stats">
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Nodes</div>
          <div className="stat-value">{total.toLocaleString()}</div>
          <div className="layer-bar">
            <div className="l2" style={{width: `${(layers.l2/total)*100}%`}}/>
            <div className="l1" style={{width: `${(layers.l1/total)*100}%`}}/>
            <div className="l0" style={{width: `${(layers.l0/total)*100}%`}}/>
          </div>
          <div className="layer-leg">
            <span><i style={{background:'#6C63FF'}}/>L2 · {layers.l2}</span>
            <span><i style={{background:'#00D4AA'}}/>L1 · {layers.l1}</span>
            <span><i style={{background:'#8B90A7'}}/>L0 · {layers.l0}</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Documents</div>
          <div className="stat-value">{stats.documents}</div>
          <div className="stat-sub">indexed · {stats.lastIndex}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Queries</div>
          <div className="stat-value">{stats.queries}</div>
          <div className="stat-sub">answered · last 7d</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Cache Hit Rate</div>
          <div className="stat-value" style={{color:'var(--secondary)'}}>{stats.cacheHit}%</div>
          <div className="stat-sub">↑ 4.2% vs yesterday</div>
        </div>
      </div>

      <div className="qph-card">
        <div style={{display:'flex', justifyContent:'space-between'}}>
          <div className="stat-label">Queries per hour</div>
          <div className="stat-sub mono">last 24h</div>
        </div>
        <div className="qph-bars">
          {stats.queriesPerHour.map((v, i) => (
            <div key={i} className="qph-bar" style={{height: `${(v/Math.max(...stats.queriesPerHour))*100}%`}} title={`${v} queries`}/>
          ))}
        </div>
        <div className="qph-axis">
          <span>00</span><span>06</span><span>12</span><span>18</span><span>now</span>
        </div>
      </div>
    </div>
  );
}

function SourcesTab({ sources, onDelete }) {
  const iconType = (name) => {
    const ext = name.split('.').pop().toLowerCase();
    if (ext === 'pdf') return 'pdf';
    if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') return 'xlsx';
    if (ext === 'docx' || ext === 'doc') return 'docx';
    if (ext === 'html' || ext === 'htm') return 'html';
    return 'txt';
  };
  return (
    <div className="sources">
      {sources.map(s => (
        <div key={s.id} className="source-item">
          <div className={"src-icon " + iconType(s.name)}>{iconType(s.name).toUpperCase()}</div>
          <div className="src-info">
            <div className="src-name">{s.name}</div>
            <div className="src-meta">{s.uploaded} · {s.size}</div>
          </div>
          <span className="src-chunks">{s.chunks} chunks</span>
          <button className="src-del" onClick={() => onDelete(s.id)} title="Remove document">
            <Icon name="trash" size={14}/>
          </button>
        </div>
      ))}
    </div>
  );
}

window.StatsTab = StatsTab;
window.SourcesTab = SourcesTab;
