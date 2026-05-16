const { useState: useStateN, useEffect: useEffectN, useRef: useRefN } = React;

// Pre-canned demo conversation history
const seedMessages = [
  {
    id: 'm1', kind: 'user',
    text: "What was Apple's revenue last quarter and how did it compare to the prior year?",
  },
  {
    id: 'm2', kind: 'ai',
    intent: 'factual_lookup',
    sources: 7,
    validated: true,
    retries: 0,
    cached: false,
    text: `Apple reported total revenue of $85.78 billion for Q3 2024 [Source 1], up 4.9% year-over-year from $81.80 billion in the same quarter of 2023 [Source 2]. Services revenue led the growth at $24.21 billion, a 14% increase [Source 3], while iPhone revenue was roughly flat at $39.30 billion [Source 4].`,
    trace: {
      total: '4.3s',
      traceId: 'a3b98b77-9c41-4e0d',
      rows: [
        { name: 'Intent Agent', passed: true, timing: '342ms', badges: [{text:'factual_lookup', tone:'pill-purple'}], subs: ['Sub-queries: ["What was Apple revenue last quarter?"]'] },
        { name: 'Retrieval Agent', passed: true, timing: '1.1s', badges: [{text:'7 chunks', tone:'pill-grey'}], subs: ['BM25: 3 | Vector: 7 | After grading: 7', 'Query rewrites: 0'] },
        { name: 'Reasoning Agent', passed: true, timing: '1.8s', badges: [{text:'987 tokens', tone:'pill-grey'}, {text:'gpt-4o', tone:'pill-purple'}], subs: ['Model: gpt-4o | Temp: 0.0'] },
        { name: 'Validation Agent', passed: true, timing: '1.1s', badges: [{text:'✓ PASSED', tone:'pill-teal'}], subs: ['0 unsupported claims · 4/4 citations grounded'] },
      ],
    },
  },
  {
    id: 'm3', kind: 'user',
    text: "Across these earnings calls, what's the dominant narrative around Apple Intelligence?",
  },
  {
    id: 'm4', kind: 'ai',
    intent: 'multi_hop',
    sources: 12,
    validated: false,
    retries: 2,
    cached: false,
    text: `Across the last three earnings calls, management has consistently framed Apple Intelligence as a multi-year platform investment rather than a single product release [Source 1][Source 4]. Tim Cook emphasized on-device privacy and the Private Cloud Compute architecture as differentiators from competitors [Source 7]. However, analyst Q&A has surfaced concerns about a delayed Siri overhaul and uneven feature availability across regions, particularly the EU and China [Source 9][Source 11]. One claim about a specific September 2025 rollout date could not be verified against the indexed sources.`,
    trace: {
      total: '6.8s',
      traceId: 'd7e21c43-1b88-4ff2',
      rows: [
        { name: 'Intent Agent', passed: true, timing: '418ms', badges: [{text:'multi_hop', tone:'pill-purple'}], subs: ['Sub-queries: ["AI strategy narrative", "Siri rollout timeline", "regional availability"]'] },
        { name: 'Retrieval Agent', passed: true, timing: '2.3s', badges: [{text:'12 chunks', tone:'pill-grey'}], subs: ['BM25: 6 | Vector: 14 | After grading: 12', 'Query rewrites: 1'] },
        { name: 'Reasoning Agent', passed: true, timing: '2.9s', badges: [{text:'1,842 tokens', tone:'pill-grey'}, {text:'gpt-4o', tone:'pill-purple'}], subs: ['Model: gpt-4o | Temp: 0.0'] },
        { name: 'Validation Agent', passed: false, timing: '1.2s', badges: [{text:'⚠ UNVERIFIED', tone:'pill-amber'}, {text:'2 retries', tone:'pill-amber'}], subs: ['1 unsupported claim · "September 2025 rollout date"', 'Retried with stricter retrieval × 2'] },
      ],
    },
  },
];

const seedStats = {
  layerBreakdown: { l2: 3, l1: 7, l0: 24 },
  documents: 4,
  lastIndex: '2h ago',
  queries: 142,
  cacheHit: 38,
  queriesPerHour: [1,0,0,1,2,1,3,5,9,12,11,8,14,18,22,17,16,11,9,7,5,4,3,6],
};

const seedSources = [
  { id:'s1', name:'Apple_10-Q_Q3-2024.pdf', uploaded:'2h ago', size:'2.4 MB', chunks: 86 },
  { id:'s2', name:'Earnings_Call_Transcript.docx', uploaded:'2h ago', size:'186 KB', chunks: 24 },
  { id:'s3', name:'Revenue_Breakdown.xlsx', uploaded:'1h ago', size:'512 KB', chunks: 12 },
  { id:'s4', name:'Analyst_Notes.txt', uploaded:'45m ago', size:'24 KB', chunks: 6 },
];

function NotebookView({ notebook, onAddDocument }) {
  const [messages, setMessages] = useStateN(seedMessages);
  const [tab, setTab] = useStateN('map');
  const [openTraces, setOpenTraces] = useStateN(new Set(['m4']));
  const [input, setInput] = useStateN('');
  const [streaming, setStreaming] = useStateN(null);
  const [rightSheet, setRightSheet] = useStateN(false);
  const scrollRef = useRefN(null);

  // canned streaming response
  const cannedResponse = `Looking across the chunked filings, three themes dominate the Services growth story this quarter. First, App Store revenue accelerated to a record [Source 2] driven by mobile games and subscriptions [Source 5]. Second, paid subscriptions across Apple's services reached over 1 billion [Source 3]. Third, advertising and AppleCare both delivered double-digit growth [Source 7]. Management attributed the trend to an expanding installed base [Source 1] and higher engagement per active user [Source 4].`;

  useEffectN(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  const toggleTrace = (id) => {
    setOpenTraces(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const sendQuery = (queryText) => {
    if (!queryText.trim() || streaming) return;
    const userMsg = { id: 'u-'+Date.now(), kind: 'user', text: queryText };
    setMessages(m => [...m, userMsg]);
    setInput('');
    // simulate cache hit randomly for variety
    const cacheHit = queryText.toLowerCase().includes('revenue last quarter');
    const pipelineSteps = ['intent', 'retrieval', 'reasoning', 'validation'];
    setStreaming({ step: 0, text: '', steps: pipelineSteps, cacheHit, _runId: Date.now() });
  };

  // streaming animator
  useEffectN(() => {
    if (!streaming) return;
    const text = cannedResponse;
    let stepIdx = 0;
    const stepDelays = [600, 900, 0, 800]; // intent, retrieval, reasoning (covers token stream), validation

    let cancelled = false;
    const advance = async (idx) => {
      if (cancelled) return;
      setStreaming(s => ({ ...s, step: idx }));
      if (idx === 2) {
        // token stream during reasoning
        for (let i = 1; i <= text.length; i++) {
          if (cancelled) return;
          await new Promise(r => setTimeout(r, 14 + Math.random()*12));
          setStreaming(s => s ? ({ ...s, step: 2, text: text.slice(0, i) }) : s);
        }
        await new Promise(r => setTimeout(r, 200));
        advance(3);
      } else if (idx < 4) {
        await new Promise(r => setTimeout(r, stepDelays[idx]));
        advance(idx + 1);
      } else {
        // done — commit message
        const newAi = {
          id: 'ai-'+Date.now(),
          kind: 'ai',
          intent: 'multi_hop',
          sources: 9,
          validated: true,
          retries: 0,
          cached: streaming.cacheHit,
          text,
          trace: {
            total: streaming.cacheHit ? '0.4s (cached)' : '5.4s',
            traceId: 'c8f4b9d2-2a15-4cc7',
            rows: [
              { name: 'Intent Agent', passed: true, timing: '298ms', badges: [{text:'multi_hop', tone:'pill-purple'}], subs: ['Sub-queries: ["Services growth themes", "App Store revenue trend"]'] },
              { name: 'Retrieval Agent', passed: true, timing: '1.4s', badges: [{text:'9 chunks', tone:'pill-grey'}], subs: ['BM25: 4 | Vector: 11 | After grading: 9', 'Query rewrites: 0'] },
              { name: 'Reasoning Agent', passed: true, timing: '2.5s', badges: [{text:'1,204 tokens', tone:'pill-grey'}, {text:'gpt-4o', tone:'pill-purple'}], subs: ['Model: gpt-4o | Temp: 0.0'] },
              { name: 'Validation Agent', passed: true, timing: '1.2s', badges: [{text:'✓ PASSED', tone:'pill-teal'}], subs: ['0 unsupported claims · 5/5 citations grounded'] },
            ],
          },
        };
        setMessages(m => [...m, newAi]);
        setStreaming(null);
      }
    };
    advance(0);
    return () => { cancelled = true; };
  }, [streaming?._runId]);  // start once when streaming begins

  const renderText = (text) => {
    // highlight [Source N] tokens
    const parts = text.split(/(\[Source \d+\])/g);
    return parts.map((p, i) => /\[Source \d+\]/.test(p) ? <span key={i} className="cite">{p}</span> : <React.Fragment key={i}>{p}</React.Fragment>);
  };

  return (
    <div className="notebook">
      <div className="chat-col">
        <div className="topbar">
          <Icon name="book" size={16}/>
          <div className="tb-title">{notebook.name}</div>
          <div className="tb-meta">· {notebook.docCount} docs · {notebook.totalChunks ?? 128} chunks</div>
          <div className="tb-spacer"/>
          <button className="btn-outline right-toggle-btn" onClick={() => setRightSheet(s => !s)}>
            <Icon name="map" size={14}/> Map
          </button>
          <button className="btn-outline" onClick={onAddDocument}>
            <Icon name="plus" size={14}/> Add Document
          </button>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.map((m) => (
            m.kind === 'user' ? (
              <div key={m.id} className="msg-user">{m.text}</div>
            ) : (
              <div key={m.id} className="col" style={{alignSelf:'flex-start', maxWidth:'88%'}}>
                <div className="msg-ai">
                  <div className="msg-text">{renderText(m.text)}</div>
                  <div className="msg-meta">
                    <span className="pill pill-purple">{m.intent}</span>
                    <span className="pill pill-grey">{m.sources} sources</span>
                    {m.validated
                      ? <span className="pill pill-teal"><span className="check-anim"><Icon name="check" size={11} stroke={3}/></span> Verified</span>
                      : <span className="pill pill-amber"><Icon name="alert" size={11}/> Unverified</span>
                    }
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
            )
          ))}

          {streaming && (
            <div className="pipeline-card">
              <div className="pipeline">
                {['Intent','Retrieval','Reasoning','Validation'].map((label, i) => {
                  const state = i < streaming.step ? 'done' : i === streaming.step ? 'active' : 'pending';
                  return (
                    <React.Fragment key={label}>
                      <div className={"pl-step " + state}>
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
            <textarea
              rows={1}
              placeholder="Ask anything about your documents..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendQuery(input);
                }
              }}
              disabled={!!streaming}
            />
            <button className="send-btn" onClick={() => sendQuery(input)} disabled={!input.trim() || !!streaming}>
              <Icon name="send" size={14} stroke={2.2}/>
            </button>
          </div>
          <div className="input-foot">
            <span>Powered by 4 specialized AI agents · RAPTOR hierarchical retrieval</span>
            <span><kbd>↵</kbd> send · <kbd>⇧↵</kbd> newline</span>
          </div>
        </div>
      </div>

      <div className={"right-col " + (rightSheet ? 'open-as-sheet' : '')}>
        <div className="tabs">
          <button className={"tab " + (tab==='map'?'active':'')} onClick={() => setTab('map')}>Knowledge Map</button>
          <button className={"tab " + (tab==='stats'?'active':'')} onClick={() => setTab('stats')}>Stats</button>
          <button className={"tab " + (tab==='sources'?'active':'')} onClick={() => setTab('sources')}>Sources</button>
          <div style={{flex:1}}/>
          {rightSheet && (
            <button className="icon-btn" style={{marginRight:6}} onClick={() => setRightSheet(false)}>
              <Icon name="x" size={14}/>
            </button>
          )}
        </div>
        <div className="tab-pane">
          {tab === 'map' && <KnowledgeMap/>}
          {tab === 'stats' && <StatsTab stats={seedStats}/>}
          {tab === 'sources' && <SourcesTab sources={seedSources} onDelete={() => {}}/>}
        </div>
      </div>
    </div>
  );
}

window.NotebookView = NotebookView;
window.seedStats = seedStats;
window.seedSources = seedSources;
