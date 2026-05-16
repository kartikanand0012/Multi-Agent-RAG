function AgentTrace({ trace, onClose }) {
  const rows = trace.rows || [];
  return (
    <div className="trace">
      <div className="trace-head">
        <h4>Agent Trace</h4>
        <button className="icon-btn" onClick={onClose} title="Close trace">
          <Icon name="x" size={14}/>
        </button>
      </div>
      <div className="trace-rows">
        {rows.map((r, i) => (
          <div key={i} className={"trace-row " + (r.passed ? 'pass' : '')}>
            <div className="trace-row-main">
              <div className="trace-num">{i+1}</div>
              <div className="trace-name">{r.name}</div>
              <div className="trace-pills">
                {r.badges.map((b, j) => (
                  <span key={j} className={"pill " + b.tone}>{b.text}</span>
                ))}
              </div>
              <div className="trace-time">{r.timing}</div>
            </div>
            {r.subs && r.subs.length > 0 && (
              <div className="trace-sub">
                {r.subs.map((s, j) => (
                  <div key={j}><span className="arrow">╰─</span> {s}</div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="trace-foot">
        <span>Total: <b style={{color:'var(--text)'}}>{trace.total}</b></span>
        <span>·</span>
        <span>Trace ID: <span style={{color:'var(--text)'}}>{trace.traceId}</span></span>
        <a href="#" onClick={(e) => e.preventDefault()}>
          Open in Langfuse <Icon name="externalLink" size={11}/>
        </a>
      </div>
    </div>
  );
}

window.AgentTrace = AgentTrace;
