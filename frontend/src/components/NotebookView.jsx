import React, { useState, useEffect, useRef } from 'react';
import Icon from './Icons';
import AgentTrace from './AgentTrace';
import KnowledgeMap from './KnowledgeMap';
import { streamQuery, fetchStats } from '../services/api';

function renderText(text) {
  const parts = text.split(/(\[Source \d+\])/g);
  return parts.map((p, i) =>
    /\[Source \d+\]/.test(p)
      ? <span key={i} className="cite">{p}</span>
      : <React.Fragment key={i}>{p}</React.Fragment>
  );
}

const PIPELINE_LABELS = ['Intent', 'Retrieval', 'Reasoning', 'Validation'];

export default function NotebookView({ notebook, onAddDocument }) {
  const [messages, setMessages] = useState([]);
  const [tab, setTab] = useState('map');
  const [openTraces, setOpenTraces] = useState(new Set());
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(null); // null | { step, text, intentType, sourcesFound }
  const [stats, setStats] = useState(null);
  const [rightOpen, setRightOpen] = useState(false);
  const scrollRef = useRef(null);
  const abortRef = useRef(null);

  // Load stats on mount and after uploads
  useEffect(() => {
    fetchStats(notebook.id)
      .then(setStats)
      .catch(() => setStats(null));
  }, [notebook.id, notebook.docCount]);

  // Auto-scroll chat
  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, streaming?.text]);

  const toggleTrace = id =>
    setOpenTraces(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const sendQuery = text => {
    if (!text.trim() || streaming) return;
    setInput('');

    const userMsg = { id: `u-${Date.now()}`, kind: 'user', text };
    setMessages(m => [...m, userMsg]);

    // Build the AI message shell — we'll fill it in as SSE events arrive
    const aiId = `ai-${Date.now()}`;
    let fullText = '';
    let intentType = 'factual_lookup';
    let sourcesFound = 0;
    let validationPassed = true;
    let retries = 0;

    setStreaming({ step: 0, text: '', intentType, sourcesFound });

    abortRef.current = streamQuery(text, notebook.id, {
      onIntent: e => {
        intentType = e.intent_type;
        setStreaming(s => ({ ...s, step: 1, intentType }));
      },
      onRetrieval: e => {
        sourcesFound = e.sources_found;
        setStreaming(s => ({ ...s, step: 2, sourcesFound }));
      },
      onToken: chunk => {
        fullText += chunk;
        setStreaming(s => ({ ...s, step: 2, text: fullText }));
      },
      onValidation: e => {
        validationPassed = e.passed;
        setStreaming(s => ({ ...s, step: 3 }));
      },
      onDone: () => {
        const aiMsg = {
          id: aiId, kind: 'ai',
          text: fullText,
          intent: intentType,
          sources: sourcesFound,
          validated: validationPassed,
          retries,
          cached: false,
          trace: {
            total: 'see Langfuse',
            traceId: null,
            rows: [
              { name: 'Intent Agent',     passed: true, timing: '—', badges: [{ text: intentType, tone: 'pill-purple' }], subs: [] },
              { name: 'Retrieval Agent',  passed: true, timing: '—', badges: [{ text: `${sourcesFound} chunks`, tone: 'pill-grey' }], subs: [] },
              { name: 'Reasoning Agent',  passed: true, timing: '—', badges: [{ text: 'gpt-4o', tone: 'pill-purple' }], subs: [] },
              { name: 'Validation Agent', passed: validationPassed, timing: '—',
                badges: [{ text: validationPassed ? '✓ PASSED' : '⚠ UNVERIFIED', tone: validationPassed ? 'pill-teal' : 'pill-amber' }], subs: [] },
            ],
          },
        };
        setMessages(m => [...m, aiMsg]);
        setStreaming(null);
      },
      onError: msg => {
        setMessages(m => [...m, { id: aiId, kind: 'error', text: msg }]);
        setStreaming(null);
      },
    });
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    setStreaming(null);
  };

  return (
    <div className="notebook">
      {/* ── Chat column ─────────────────────────────────────── */}
      <div className="chat-col">
        <div className="topbar">
          <Icon name="book" size={16}/>
          <div className="tb-title">{notebook.name}</div>
          <div className="tb-meta">
            · {notebook.docCount} docs
            {stats && ` · ${stats.total_nodes} nodes`}
          </div>
          <div className="tb-spacer"/>
          <button className="btn-outline right-toggle-btn" onClick={() => setRightOpen(o => !o)}>
            <Icon name="map" size={14}/> Map
          </button>
          <button className="btn-outline" onClick={onAddDocument}>
            <Icon name="plus" size={14}/> Add Document
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
            if (m.kind === 'user')
              return <div key={m.id} className="msg-user">{m.text}</div>;
            if (m.kind === 'error')
              return <div key={m.id} className="msg-error"><Icon name="alert" size={13}/> {m.text}</div>;
            return (
              <div key={m.id} className="col" style={{ alignSelf: 'flex-start', maxWidth: '88%' }}>
                <div className="msg-ai">
                  <div className="msg-text">{renderText(m.text)}</div>
                  <div className="msg-meta">
                    <span className="pill pill-purple">{m.intent}</span>
                    <span className="pill pill-grey">{m.sources} sources</span>
                    {m.validated
                      ? <span className="pill pill-teal"><Icon name="check" size={11} stroke={3}/> Verified</span>
                      : <span className="pill pill-amber"><Icon name="alert" size={11}/> Unverified</span>}
                    {m.retries > 0 && <span className="pill pill-amber">{m.retries} retries</span>}
                    {m.cached && <span className="pill pill-lightning"><Icon name="bolt" size={11}/> Cache hit</span>}
                    <button className="msg-expand" onClick={() => toggleTrace(m.id)}>
                      {openTraces.has(m.id) ? 'Hide' : 'View'} agent trace
                      <Icon name={openTraces.has(m.id) ? 'chevronUp' : 'chevronDown'} size={12}/>
                    </button>
                  </div>
                  {openTraces.has(m.id) && (
                    <AgentTrace trace={m.trace} onClose={() => toggleTrace(m.id)}/>
                  )}
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
                <div className="pipeline-stream">
                  {renderText(streaming.text)}
                  <span className="cursor"/>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="input-bar">
          <div className="input-wrap">
            <textarea rows={1} placeholder="Ask anything about your documents…"
              value={input} onChange={e => setInput(e.target.value)}
              disabled={!!streaming}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(input); } }}
            />
            {streaming
              ? <button className="send-btn stop-btn" onClick={stopStreaming}><Icon name="x" size={14}/></button>
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

      {/* ── Right panel ──────────────────────────────────────── */}
      <div className={`right-col ${rightOpen ? 'open-as-sheet' : ''}`}>
        <div className="tabs">
          {['map', 'stats', 'sources'].map(t => (
            <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
          <div style={{ flex: 1 }}/>
          {rightOpen && <button className="icon-btn" onClick={() => setRightOpen(false)}><Icon name="x" size={14}/></button>}
        </div>
        <div className="tab-pane">
          {tab === 'map' && <KnowledgeMap notebookId={notebook.id}/>}
          {tab === 'stats' && <StatsTab stats={stats}/>}
          {tab === 'sources' && <SourcesTab notebookId={notebook.id}/>}
        </div>
      </div>
    </div>
  );
}

function StatsTab({ stats }) {
  if (!stats) return <div className="tab-empty">Loading stats…</div>;
  return (
    <div className="stats-tab">
      <div className="stat-cards">
        <div className="stat-card">
          <div className="stat-value">{stats.total_nodes}</div>
          <div className="stat-label">Total nodes</div>
        </div>
        {Object.entries(stats.layer_breakdown || {}).map(([layer, count]) => (
          <div key={layer} className="stat-card">
            <div className="stat-value">{count}</div>
            <div className="stat-label">Layer {layer} nodes</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SourcesTab({ notebookId }) {
  return (
    <div className="tab-empty">
      <Icon name="file" size={24} stroke={1.5}/>
      <div>Upload documents to see sources</div>
    </div>
  );
}
