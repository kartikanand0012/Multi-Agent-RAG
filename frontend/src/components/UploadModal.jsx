import React, { useState, useEffect, useRef } from 'react';
import Icon from './Icons';
import { uploadFile } from '../services/api';

function ProgRow({ label, pct, done, pending, spinner }) {
  return (
    <div className={"prog-row " + (done ? 'done' : pending ? 'pending' : '')}>
      <div className="prog-head">
        <b>
          {spinner && <span className="spinner" style={{ marginRight: 8, verticalAlign: -2 }}/>}
          {done && <Icon name="check" size={12} stroke={3} style={{ marginRight: 6, color: 'var(--secondary)' }}/>}
          {label}{pending ? ' · waiting' : ''}
        </b>
        <span className="prog-pct">{done ? '100%' : pending ? '—' : `${Math.round(pct)}%`}</span>
      </div>
      <div className="prog-bar">
        <div className={"prog-fill " + (done ? 'done' : '')} style={{ width: `${pct}%` }}/>
      </div>
    </div>
  );
}

export default function UploadModal({ notebookName, mode = 'add', onClose, onComplete }) {
  const [files, setFiles] = useState([]);
  const [raptor, setRaptor] = useState(true);
  const [target, setTarget] = useState(mode);
  const [newName, setNewName] = useState('');
  const [drag, setDrag] = useState(false);
  const [phase, setPhase] = useState('idle'); // idle | uploading | chunking | tree | done
  const [pct, setPct] = useState({ upload: 0, chunk: 0, tree: 0 });
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  // Animate progress bars
  useEffect(() => {
    if (phase === 'idle' || phase === 'done') return;
    let t;
    if (phase === 'uploading') {
      t = setInterval(() => setPct(p => {
        const v = Math.min(90, p.upload + 18 + Math.random() * 8);
        return { ...p, upload: v };
      }), 180);
    } else if (phase === 'chunking') {
      t = setInterval(() => setPct(p => {
        const v = Math.min(100, p.chunk + 14 + Math.random() * 6);
        return { ...p, chunk: v };
      }), 200);
    } else if (phase === 'tree') {
      t = setInterval(() => setPct(p => {
        const v = Math.min(95, p.tree + 6 + Math.random() * 4);
        return { ...p, tree: v };
      }), 280);
    }
    return () => clearInterval(t);
  }, [phase]);

  const addFiles = newFiles => setFiles(f => [...f, ...newFiles].slice(0, 5));

  const start = async () => {
    if (!files.length) { setError('Please select at least one file'); return; }
    const nbId = target === 'new'
      ? (newName.trim() || 'my-notebook').toLowerCase().replace(/\s+/g, '-')
      : (notebookName || 'default').toLowerCase().replace(/\s+/g, '-');

    setError(null);
    setPhase('uploading');
    setPct({ upload: 0, chunk: 0, tree: 0 });

    try {
      // Upload
      await new Promise(r => setTimeout(r, 600));
      setPct(p => ({ ...p, upload: 100 }));
      setPhase('chunking');

      await new Promise(r => setTimeout(r, 400));
      setPct(p => ({ ...p, chunk: 100 }));
      setPhase('tree');

      const result = await uploadFile(files[0], nbId, raptor);

      setPct(p => ({ ...p, tree: 100 }));
      setPhase('done');

      setTimeout(() => {
        onComplete({
          newNotebook: target === 'new' ? (newName.trim() || 'Untitled Notebook') : null,
          notebookId: nbId,
          files,
          result,
        });
      }, 900);
    } catch (e) {
      setPhase('idle');
      setError(e.response?.data?.detail || e.message || 'Upload failed. Please try again.');
    }
  };

  return (
    <div className="modal-overlay" onClick={phase === 'idle' ? onClose : undefined}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{target === 'new' ? 'Create New Notebook' : `Add Documents to ${notebookName || 'Notebook'}`}</h2>
          {phase === 'idle' && <button className="icon-btn" onClick={onClose}><Icon name="x" size={16}/></button>}
        </div>

        <div className="modal-body">
          {phase === 'idle' && (
            <>
              <div
                className={"dropzone " + (drag ? 'drag' : '')}
                onDragOver={e => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={e => { e.preventDefault(); setDrag(false); addFiles(Array.from(e.dataTransfer.files)); }}
                onClick={() => inputRef.current?.click()}
              >
                <input ref={inputRef} type="file" hidden multiple
                  accept=".pdf,.docx,.xlsx,.xls,.txt,.md,.htm,.html"
                  onChange={e => addFiles(Array.from(e.target.files))} />
                <div className="dz-icon"><Icon name="cloud" size={28}/></div>
                <div className="dz-title">Drag files here or click to browse</div>
                <div className="dz-sub">PDF · DOCX · XLSX · TXT · HTML</div>
              </div>

              <div className="or-div">OR</div>
              <button className="btn-outline" style={{ justifyContent: 'center', width: '100%' }} onClick={() => inputRef.current?.click()}>
                <Icon name="file" size={14}/> Browse Files
              </button>

              {files.length > 0 && (
                <div className="col" style={{ gap: 6, marginTop: 8 }}>
                  {files.map((f, i) => {
                    const ext = f.name.split('.').pop().toLowerCase();
                    const cls = ext === 'pdf' ? 'pdf' : ext === 'xlsx' || ext === 'xls' ? 'xlsx' : ext === 'docx' ? 'docx' : 'txt';
                    return (
                      <div key={i} className="file-row">
                        <div className={`src-icon ${cls}`}>{ext.toUpperCase()}</div>
                        <div className="src-info">
                          <div className="src-name">{f.name}</div>
                          <div className="src-meta">{(f.size / 1024).toFixed(0)} KB</div>
                        </div>
                        <button className="file-x" onClick={() => setFiles(fs => fs.filter((_, j) => j !== i))}>
                          <Icon name="x" size={14}/>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="col" style={{ gap: 0, marginTop: 4 }}>
                <div className="opt-row">
                  <div className="opt-info">
                    <b>Use RAPTOR hierarchical indexing
                      <span className="tooltip-q" title="Builds a summary tree for better thematic understanding across long documents.">?</span>
                    </b>
                    <span>Builds a summary tree for better thematic understanding.</span>
                  </div>
                  <button className={"toggle " + (raptor ? 'on' : '')} onClick={() => setRaptor(r => !r)}/>
                </div>

                <div className="opt-row">
                  <div className="opt-info" style={{ flex: 1 }}>
                    <b>Destination</b>
                    <div className="seg" style={{ marginTop: 6, maxWidth: 280 }}>
                      <button className={target === 'add' ? 'on' : ''} onClick={() => setTarget('add')}>Add to existing</button>
                      <button className={target === 'new' ? 'on' : ''} onClick={() => setTarget('new')}>Create new</button>
                    </div>
                    {target === 'new' && (
                      <input className="modal-input" style={{ marginTop: 10, maxWidth: 320 }}
                        placeholder="Notebook name" value={newName} onChange={e => setNewName(e.target.value)} />
                    )}
                  </div>
                </div>
              </div>

              {error && <div style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{error}</div>}
            </>
          )}

          {phase !== 'idle' && (
            <div className="prog-list">
              <ProgRow label="Uploading files" pct={pct.upload} done={pct.upload >= 100}/>
              <ProgRow label="Chunking documents" pct={pct.chunk} done={pct.chunk >= 100} pending={phase === 'uploading'}/>
              {raptor && (
                <ProgRow label="Building RAPTOR tree" pct={pct.tree} done={pct.tree >= 100}
                  pending={phase === 'uploading' || phase === 'chunking'} spinner={phase === 'tree'}/>
              )}
              <div className={"prog-row " + (phase === 'done' ? 'done' : 'pending')}>
                <div className="prog-head">
                  <b>{phase === 'done' ? <><Icon name="check" size={12} stroke={3}/> Indexing complete</> : 'Indexing complete'}</b>
                  <span className="prog-pct">{phase === 'done' ? '✓' : '—'}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-foot">
          {phase === 'idle' ? (
            <>
              <button className="btn-ghost" onClick={onClose}>Cancel</button>
              <button className="btn-primary" onClick={start}
                disabled={target === 'new' && !newName.trim()}
                style={{ opacity: target === 'new' && !newName.trim() ? 0.5 : 1, flex: 1 }}>
                <Icon name="upload" size={14}/> Upload &amp; Index
              </button>
            </>
          ) : (
            <button className="btn-ghost" onClick={onClose} disabled={phase !== 'done'}
              style={{ opacity: phase === 'done' ? 1 : 0.5 }}>
              {phase === 'done' ? 'Done' : 'Indexing…'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
