const { useState: useStateU, useEffect: useEffectU } = React;

function UploadModal({ notebookName, onClose, onComplete, mode='add' }) {
  const [files, setFiles] = useStateU([]);
  const [raptor, setRaptor] = useStateU(true);
  const [target, setTarget] = useStateU(mode); // 'add' | 'new'
  const [newName, setNewName] = useStateU('');
  const [drag, setDrag] = useStateU(false);
  const [phase, setPhase] = useStateU('idle'); // idle | uploading | chunking | tree | done
  const [pct, setPct] = useStateU({ upload: 0, chunk: 0, tree: 0 });

  const addFakeFile = () => {
    const samples = [
      { name: 'Apple_10-Q_Q3-2024.pdf', size: '2.4 MB' },
      { name: 'Earnings_Call_Transcript.docx', size: '186 KB' },
      { name: 'Revenue_Breakdown.xlsx', size: '512 KB' },
      { name: 'Analyst_Notes.txt', size: '24 KB' },
    ];
    const s = samples[files.length % samples.length];
    setFiles(f => [...f, { id: Date.now()+Math.random(), ...s }]);
  };
  const removeFile = (id) => setFiles(f => f.filter(x => x.id !== id));

  useEffectU(() => {
    if (phase === 'idle' || phase === 'done') return;
    let t;
    if (phase === 'uploading') {
      t = setInterval(() => setPct(p => {
        const v = Math.min(100, p.upload + 18 + Math.random() * 8);
        if (v >= 100) { clearInterval(t); setTimeout(() => setPhase('chunking'), 250); }
        return { ...p, upload: v };
      }), 180);
    } else if (phase === 'chunking') {
      t = setInterval(() => setPct(p => {
        const v = Math.min(100, p.chunk + 14 + Math.random() * 6);
        if (v >= 100) { clearInterval(t); setTimeout(() => setPhase('tree'), 250); }
        return { ...p, chunk: v };
      }), 200);
    } else if (phase === 'tree') {
      t = setInterval(() => setPct(p => {
        const v = Math.min(100, p.tree + 6 + Math.random() * 4);
        if (v >= 100) { clearInterval(t); setTimeout(() => setPhase('done'), 350); }
        return { ...p, tree: v };
      }), 280);
    }
    return () => clearInterval(t);
  }, [phase]);

  useEffectU(() => {
    if (phase === 'done') {
      const t = setTimeout(() => {
        onComplete && onComplete({
          newNotebook: target === 'new' ? newName || 'Untitled notebook' : null,
          files,
        });
      }, 900);
      return () => clearTimeout(t);
    }
  }, [phase]);

  const start = () => {
    if (files.length === 0) { addFakeFile(); setTimeout(() => setPhase('uploading'), 30); return; }
    setPhase('uploading');
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDrag(false);
    addFakeFile();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{target === 'new' ? 'Create New Notebook' : `Add Documents to ${notebookName}`}</h2>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={16}/></button>
        </div>

        <div className="modal-body">
          {phase === 'idle' && (
            <React.Fragment>
              <div
                className={"dropzone " + (drag ? 'drag' : '')}
                onDragOver={e => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={handleDrop}
                onClick={addFakeFile}
              >
                <div className="dz-icon"><Icon name="cloud" size={28}/></div>
                <div className="dz-title">Drag files here or click to browse</div>
                <div className="dz-sub">PDF · DOCX · XLSX · TXT · HTML</div>
              </div>

              <div className="or-div">OR</div>
              <button className="btn-outline" style={{justifyContent:'center', width:'100%'}} onClick={addFakeFile}>
                <Icon name="file" size={14}/> Browse Files
              </button>

              {files.length > 0 && (
                <div className="col" style={{gap:6}}>
                  {files.map(f => (
                    <div key={f.id} className="file-row">
                      <div className={"src-icon " + (f.name.endsWith('.pdf')?'pdf':f.name.endsWith('.xlsx')?'xlsx':f.name.endsWith('.docx')?'docx':'txt')}>
                        {f.name.split('.').pop().toUpperCase()}
                      </div>
                      <div className="src-info">
                        <div className="src-name">{f.name}</div>
                        <div className="src-meta">{f.size}</div>
                      </div>
                      <button className="file-x" onClick={() => removeFile(f.id)}><Icon name="x" size={14}/></button>
                    </div>
                  ))}
                </div>
              )}

              <div className="col" style={{gap:0, marginTop:4}}>
                <div className="opt-row">
                  <div className="opt-info">
                    <b>
                      Use RAPTOR hierarchical indexing
                      <span className="tooltip-q" title="Builds a summary tree for better thematic understanding across long documents.">?</span>
                    </b>
                    <span>Builds a summary tree for better thematic understanding.</span>
                  </div>
                  <button className={"toggle " + (raptor ? 'on' : '')} onClick={() => setRaptor(r => !r)}/>
                </div>

                <div className="opt-row">
                  <div className="opt-info" style={{flex:1}}>
                    <b>Destination</b>
                    <div className="seg" style={{marginTop:6, maxWidth:280}}>
                      <button className={target==='add'?'on':''} onClick={() => setTarget('add')}>Add to existing</button>
                      <button className={target==='new'?'on':''} onClick={() => setTarget('new')}>Create new</button>
                    </div>
                    {target === 'new' && (
                      <input
                        className="modal-input"
                        style={{marginTop:10, maxWidth:320}}
                        placeholder="Notebook name"
                        value={newName}
                        onChange={e => setNewName(e.target.value)}
                      />
                    )}
                  </div>
                </div>
              </div>
            </React.Fragment>
          )}

          {phase !== 'idle' && (
            <div className="prog-list">
              <ProgRow label="Uploading files" pct={pct.upload} done={pct.upload >= 100}/>
              <ProgRow label="Chunking documents" pct={pct.chunk} done={pct.chunk >= 100} pending={phase==='uploading'}/>
              {raptor ? (
                <ProgRow label="Building RAPTOR tree" pct={pct.tree} done={pct.tree >= 100} pending={phase==='uploading' || phase==='chunking'} spinner={phase==='tree'}/>
              ) : null}
              <div className={"prog-row " + (phase==='done' ? 'done' : 'pending')}>
                <div className="prog-head">
                  <b>{phase === 'done' ? <><Icon name="check" size={12} stroke={3}/> Indexing complete</> : 'Indexing complete'}</b>
                  <span className="prog-pct">{phase === 'done' ? '✓' : '—'}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {phase === 'idle' ? (
          <div className="modal-foot">
            <button className="btn-ghost" onClick={onClose}>Cancel</button>
            <button
              className="btn-primary"
              onClick={start}
              disabled={target==='new' && !newName.trim()}
              style={{opacity: (target==='new' && !newName.trim()) ? 0.5 : 1, flex: 1}}
            >
              <Icon name="upload" size={14}/> Upload & Index
            </button>
          </div>
        ) : (
          <div className="modal-foot">
            <button className="btn-ghost" onClick={onClose} disabled={phase !== 'done'} style={{opacity: phase==='done'?1:0.5}}>
              {phase === 'done' ? 'Done' : 'Indexing…'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ProgRow({ label, pct, done, pending, spinner }) {
  return (
    <div className={"prog-row " + (done ? 'done' : pending ? 'pending' : '')}>
      <div className="prog-head">
        <b>
          {spinner && <span className="spinner" style={{marginRight:8, verticalAlign:-2}}></span>}
          {done && <Icon name="check" size={12} stroke={3} style={{marginRight:6, color:'var(--secondary)'}}/>}
          {label}{pending ? ' · waiting' : ''}
        </b>
        <span className="prog-pct">{done ? '100%' : pending ? '—' : `${Math.round(pct)}%`}</span>
      </div>
      <div className="prog-bar">
        <div className={"prog-fill " + (done ? 'done' : '')} style={{width: `${pct}%`}}/>
      </div>
    </div>
  );
}

window.UploadModal = UploadModal;
