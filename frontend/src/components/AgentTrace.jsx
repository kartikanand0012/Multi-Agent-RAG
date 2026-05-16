import React from 'react';
import Icon from './Icons';

export default function AgentTrace({ trace, onClose }) {
  if (!trace) return null;
  return (
    <div className="agent-trace">
      <div className="trace-header">
        <span className="trace-title">Agent Trace</span>
        <button className="icon-btn" onClick={onClose}><Icon name="x" size={13}/></button>
      </div>
      <div className="trace-rows">
        {trace.rows.map((row, i) => (
          <div className="trace-row" key={i}>
            <div className="trace-row-top">
              <span className="trace-num">{'①②③④'[i]}</span>
              <span className="trace-name">{row.name}</span>
              {row.badges.map((b, j) => (
                <span key={j} className={`pill ${b.tone}`}>{b.text}</span>
              ))}
              <span className="trace-timing">{row.timing}</span>
            </div>
            {row.subs.map((s, j) => (
              <div className="trace-sub" key={j}>╰─ {s}</div>
            ))}
          </div>
        ))}
      </div>
      <div className="trace-footer">
        <span>Total: {trace.total}</span>
        {trace.traceId && (
          <>
            <span className="trace-sep">·</span>
            <span className="trace-id">Trace: {trace.traceId.slice(0, 16)}…</span>
            {trace.langfuseUrl && (
              <a href={trace.langfuseUrl} target="_blank" rel="noreferrer" className="trace-link">
                Langfuse ↗
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}
