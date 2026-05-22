import React, { useState, useEffect, useMemo, useRef } from 'react';
import Icon from './Icons';
import AgentTrace from './AgentTrace';
import KnowledgeMap from './KnowledgeMap';
import { streamQuery, fetchStats, fetchMap } from '../services/api';

function renderText(text, onCiteClick) {
  const parts = text.split(/(\[Source \d+\])/g);
  return parts.map((p, i) =>
    /\[Source \d+\]/.test(p)
      ? <span key={i} className="cite" onClick={onCiteClick} title="Click to view sources">{p}</span>
      : <React.Fragment key={i}>{p}</React.Fragment>
  );
}

const PIPELINE_LABELS = ['Intent', 'Retrieval', 'Reasoning', 'Validation'];

function StatsTab({ stats }) {
  if (!stats) return <div className="tab-empty">Loading stats…</div>;
  const lb = stats.layer_breakdown || {};
  const l2 = lb['2'] || 0, l1 = lb['1'] || 0, l0 = lb['0'] || 0;
  const total = stats.total_nodes || 0;
  return (
    <div className="stats">
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Nodes</div>
          <div className="stat-value">{total.toLocaleString()}</div>
          {total > 0 && (
            <>
              <div className="layer-bar">
                <div className="l2" style={{ width: `${(l2 / total) * 100}%` }}/>
                <div className="l1" style={{ width: `${(l1 / total) * 100}%` }}/>
                <div className="l0" style={{ width: `${(l0 / total) * 100}%` }}/>
              </div>
              <div className="layer-leg">
                <span><i style={{ background: '#6C63FF' }}/>L2 · {l2}</span>
                <span><i style={{ background: '#00D4AA' }}/>L1 · {l1}</span>
                <span><i style={{ background: '#8B90A7' }}/>L0 · {l0}</span>
              </div>
            </>
          )}
        </div>
        <div className="stat-card">
          <div className="stat-label">Leaf Chunks</div>
          <div className="stat-value">{l0}</div>
          <div className="stat-sub">raw document chunks</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Summaries L1</div>
          <div className="stat-value" style={{ color: 'var(--secondary)' }}>{l1}</div>
          <div className="stat-sub">cluster summaries</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Summaries L2</div>
          <div className="stat-value" style={{ color: 'var(--primary)' }}>{l2}</div>
          <div className="stat-sub">top-level summaries</div>
        </div>
      </div>
    </div>
  );
}

function SourcesTab({ mapData, loading }) {
  const sources = useMemo(() => {
    if (!mapData?.nodes) return null;
    const srcMap = {};
    mapData.nodes.filter(n => n.layer === 0).forEach(n => {
      if (!n.source) return;
      const name = n.source.split(/[\\/]/).pop();
      if (!srcMap[name]) srcMap[name] = { name, chunks: 0 };
      srcMap[name].chunks++;
    });
    return Object.values(srcMap);
  }, [mapData]);

  if (loading || !sources) return <div className="tab-empty">Loading sources…</div>;

  if (!sources.length) return (
    <div className="sources">
      <div className="sources-empty">
        <Icon name="file" size={24} stroke={1.5}/>
        <div style={{ marginTop: 8, fontSize: 13 }}>Upload documents to see sources</div>
      </div>
    </div>
  );

  return (
    <div className="sources">
      {sources.map(s => {
        const ext = s.name.split('.').pop().toLowerCase();
        const cls = ['pdf','xlsx','docx','txt','html'].includes(ext) ? ext : 'txt';
        return (
          <div key={s.name} className="source-item">
            <div className={`src-icon ${cls}`}>{ext.toUpperCase().slice(0, 3)}</div>
            <div className="src-info">
              <div className="src-name">{s.name}</div>
              <div className="src-meta">{s.chunks} chunks indexed</div>
            </div>
            <span className="src-chunks">{s.chunks}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function NotebookView({ notebook, onAddDocument }) {
  const [messages, setMessages] = useState([]);
  const [tab, setTab] = useState('map');
  const [openTraces, setOpenTraces] = useState(new Set());
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(null);
  const [stats, setStats] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [mapError, setMapError] = useState(null);
  const [rightOpen, setRightOpen] = useState(false);
  const [rightWidth, setRightWidth] = useState(380);
  const scrollRef  = useRef(null);
  const abortRef   = useRef(null);
  const resizeRef  = useRef(null);

  // Resizable panel (desktop only)
  useEffect(() => {
    const onMove = e => {
      if (!resizeRef.current) return;
      const delta = resizeRef.current.startX - e.clientX; // drag left → wider
      const w = Math.max(300, Math.min(720, resizeRef.current.startW + delta));
      setRightWidth(w);
    };
    const onUp = () => { resizeRef.current = null; };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',  onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',  onUp);
    };
  }, []);

  useEffect(() => {
    fetchStats(notebook.id).then(setStats).catch(() => setStats(null));
  }, [notebook.id, notebook.docCount]);

  // Fetch map once per notebook (and refetch when docCount changes after upload).
  // Both KnowledgeMap and SourcesTab consume this — avoids two /map calls per tab switch.
  useEffect(() => {
    if (!notebook.id) return;
    let cancelled = false;
    setMapLoading(true); setMapError(null);
    fetchMap(notebook.id)
      .then(d => { if (!cancelled) { setMapData(d); setMapLoading(false); } })
      .catch(e => { if (!cancelled) { setMapError(e.message || String(e)); setMapLoading(false); } });
    return () => { cancelled = true; };
  }, [notebook.id, notebook.docCount]);

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    // include streaming.step so the pipeline card stays in view as it animates
    // through Intent → Retrieval → Reasoning → Validation, even before tokens arrive
  }, [messages, streaming?.text, streaming?.step]);

  const toggleTrace = id =>
    setOpenTraces(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const sendQuery = text => {
    if (!text.trim() || streaming) return;
    setInput('');
    setMessages(m => [...m, { id: `u-${Date.now()}`, kind: 'user', text }]);

    const aiId = `ai-${Date.now()}`;
    let fullText = '', intentType = 'factual_lookup', sourcesFound = 0;
    let validationPassed = true;
    let unsupportedClaims = [];
    let validationFeedback = '';

    setStreaming({ step: 0, text: '' });

    abortRef.current = streamQuery(text, notebook.id, {
      onIntent: e => { intentType = e.intent_type; setStreaming(s => ({ ...s, step: 1 })); },
      onRetrieval: e => { sourcesFound = e.sources_found; setStreaming(s => ({ ...s, step: 2 })); },
      onToken: chunk => { fullText += chunk; setStreaming(s => ({ ...s, step: 2, text: fullText })); },
      onValidation: e => {
        validationPassed = e.passed;
        if (Array.isArray(e.unsupported_claims)) unsupportedClaims = e.unsupported_claims;
        if (typeof e.feedback === 'string') validationFeedback = e.feedback;
        setStreaming(s => ({ ...s, step: 3 }));
      },
      onDone: () => {
        setMessages(m => [...m, {
          id: aiId, kind: 'ai', text: fullText,
          intent: intentType, sources: sourcesFound,
          validated: validationPassed, retries: 0, cached: false,
          unsupportedClaims, validationFeedback,
          trace: {
            total: 'see Langfuse', traceId: null,
            rows: [
              { name: 'Intent Agent',     passed: true,              timing: '—', badges: [{ text: intentType,          tone: 'pill-purple' }], subs: [] },
              { name: 'Retrieval Agent',  passed: true,              timing: '—', badges: [{ text: `${sourcesFound} chunks`, tone: 'pill-grey'   }], subs: [] },
              { name: 'Reasoning Agent',  passed: true,              timing: '—', badges: [{ text: 'gpt-4o',             tone: 'pill-purple' }], subs: [] },
              { name: 'Validation Agent', passed: validationPassed,  timing: '—', badges: [{ text: validationPassed ? '✓ PASSED' : '⚠ UNVERIFIED', tone: validationPassed ? 'pill-teal' : 'pill-amber' }], subs: [] },
            ],
          },
        }]);
        setStreaming(null);
      },
      onError: msg => {
        setMessages(m => [...m, { id: aiId, kind: 'error', text: msg }]);
        setStreaming(null);
      },
    });
  };

  return (
    <div className="notebook">
      {/* Chat column */}
      <div className="chat-col">
        <div className="topbar">
          <Icon name="book" size={16}/>
          <div className="tb-title">{notebook.name}</div>
          <div className="tb-meta">· {notebook.docCount} docs{stats ? ` · ${stats.total_nodes} nodes` : ''}</div>
          <div className="tb-spacer"/>
          <button className="btn-outline right-toggle-btn" onClick={() => setRightOpen(o => !o)}>
            <Icon name="map" size={14}/><span className="btn-label"> Map</span>
          </button>
          <button className="btn-outline" onClick={onAddDocument}>
            <Icon name="plus" size={14}/><span className="btn-label"> Add Document</span>
          </button>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 && !streaming && (
            <div className="chat-empty">
              <Icon name="search" size={28} stroke={1.5}/>
              <div>Ask anything about your documents</div>
              <div className="chat-empty-hint">Powered by 4 specialized AI agents + RAPTOR indexing</div>
            </div>
          )}

          {messages.map(m => {
            if (m.kind === 'user') return <div key={m.id} className="msg-user">{m.text}</div>;
            if (m.kind === 'error') return (
              <div key={m.id} className="msg-ai" style={{ borderColor: 'var(--danger-dim)', maxWidth: '88%', alignSelf: 'flex-start' }}>
                <div className="msg-text" style={{ color: 'var(--danger)' }}><Icon name="alert" size={13}/> {m.text}</div>
              </div>
            );
            return (
              <div key={m.id} className="col" style={{ alignSelf: 'flex-start', maxWidth: '88%' }}>
                <div className="msg-ai">
                  <div className="msg-text">{renderText(m.text, () => { setTab('sources'); setRightOpen(true); })}</div>
                  <div className="msg-meta">
                    <span className="pill pill-purple">{m.intent}</span>
                    <span className="pill pill-grey">{m.sources} sources</span>
                    {m.validated
                      ? <span className="pill pill-teal"><span className="check-anim"><Icon name="check" size={11} stroke={3}/></span> Verified</span>
                      : <span className="pill pill-amber"
                          title={m.validationFeedback || 'One or more claims could not be verified against the source documents.'}>
                          <Icon name="alert" size={11}/> Unverified
                        </span>}
                    {m.retries > 0 && <span className="pill pill-amber">{m.retries} retries</span>}
                    {m.cached && <span className="pill pill-lightning"><Icon name="bolt" size={11}/> Cache hit</span>}
                    <button className="msg-expand" onClick={() => toggleTrace(m.id)}>
                      {openTraces.has(m.id) ? 'Hide' : 'View'} agent trace
                      <Icon name={openTraces.has(m.id) ? 'chevronUp' : 'chevronDown'} size={12}/>
                    </button>
                  </div>
                  {!m.validated && (m.unsupportedClaims?.length > 0 || m.validationFeedback) && (
                    <div className="validation-note">
                      <div className="validation-note-head">
                        <Icon name="alert" size={12}/> Unverified claims
                      </div>
                      {m.validationFeedback && <div className="validation-note-feedback">{m.validationFeedback}</div>}
                      {m.unsupportedClaims?.length > 0 && (
                        <ul className="validation-note-list">
                          {m.unsupportedClaims.slice(0, 4).map((c, i) => <li key={i}>{c}</li>)}
                        </ul>
                      )}
                    </div>
                  )}
                  {openTraces.has(m.id) && <AgentTrace trace={m.trace} onClose={() => toggleTrace(m.id)}/>}
                </div>
              </div>
            );
          })}

          {streaming && (
            <div className="pipeline-card">
              <div className="pipeline">
                {PIPELINE_LABELS.map((label, i) => {
                  const state = i < streaming.step ? 'done' : i === streaming.step ? 'active' : 'pending';
                  return (
                    <React.Fragment key={label}>
                      <div className={`pl-step ${state}`}>
                        <span className="pl-dot"/>
                        {label}
                        {state === 'done' && <Icon name="check" size={10} stroke={3}/>}
                      </div>
                      {i < 3 && <span className="pl-arrow">→</span>}
                    </React.Fragment>
                  );
                })}
              </div>
              {streaming.text && (
                <div className="pipeline-stream">{renderText(streaming.text, null)}<span className="cursor"/></div>
              )}
            </div>
          )}
        </div>

        <div className="input-bar">
          <div className="input-wrap">
            <textarea rows={1} placeholder="Ask anything about your documents…"
              value={input} onChange={e => setInput(e.target.value)} disabled={!!streaming}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(input); } }}
            />
            {streaming
              ? <button className="send-btn" onClick={() => { abortRef.current?.abort(); setStreaming(null); }}><Icon name="x" size={14}/></button>
              : <button className="send-btn" onClick={() => sendQuery(input)} disabled={!input.trim()}>
                  <Icon name="send" size={14} stroke={2.2}/>
                </button>
            }
          </div>
          <div className="input-foot">
            <span>Powered by 4 specialized AI agents · RAPTOR hierarchical retrieval</span>
            <span><kbd>↵</kbd> send · <kbd>⇧↵</kbd> newline</span>
          </div>
        </div>
      </div>

      {/* Resize handle — desktop only, hidden when sheet is open */}
      {!rightOpen && (
        <div className="resize-handle"
          onMouseDown={e => { resizeRef.current = { startX: e.clientX, startW: rightWidth }; }}
          title="Drag to resize panel"
        />
      )}

      {/* Right panel */}
      <div className={"right-col " + (rightOpen ? 'open-as-sheet' : '')}
        style={rightOpen ? {} : { width: rightWidth }}>
        <div className="tabs">
          {[['map', 'Knowledge Map'], ['stats', 'Stats'], ['sources', 'Sources']].map(([t, label]) => (
            <button key={t} className={"tab " + (tab === t ? 'active' : '')} onClick={() => setTab(t)}>{label}</button>
          ))}
          <div style={{ flex: 1 }}/>
          {rightOpen && <button className="icon-btn" style={{ marginRight: 6 }} onClick={() => setRightOpen(false)}><Icon name="x" size={14}/></button>}
        </div>
        <div className="tab-pane">
          {tab === 'map' && <KnowledgeMap data={mapData} loading={mapLoading} error={mapError}/>}
          {tab === 'stats' && <StatsTab stats={stats}/>}
          {tab === 'sources' && <SourcesTab mapData={mapData} loading={mapLoading}/>}
        </div>
      </div>
    </div>
  );
}
