import React, { useState, useRef } from 'react';
import Icon from './Icons';
import { uploadFile } from '../services/api';

const STEPS = ['Uploading file…', 'Chunking document…', 'Building RAPTOR tree…', 'Indexing complete ✓'];

export default function UploadModal({ notebookName, mode, onClose, onComplete }) {
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [newName, setNewName] = useState('');
  const [useRaptor, setUseRaptor] = useState(true);
  const [step, setStep] = useState(-1); // -1 = idle, 0-3 = progress
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const accept = '.pdf,.docx,.xlsx,.xls,.txt,.md,.htm,.html';

  const handleDrop = e => {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files);
    setFiles(dropped.slice(0, 5));
  };

  const handleUpload = async () => {
    if (!files.length) return;
    const nbId = mode === 'new'
      ? (newName.trim() || 'my-notebook').toLowerCase().replace(/\s+/g, '-')
      : notebookName?.toLowerCase().replace(/\s+/g, '-') || 'default';

    setError(null);
    setStep(0);

    try {
      // Simulate chunking step (happens server-side, just animate)
      await new Promise(r => setTimeout(r, 600));
      setStep(1);
      await new Promise(r => setTimeout(r, 400));
      setStep(2);

      const result = await uploadFile(files[0], nbId, useRaptor);

      setStep(3);
      await new Promise(r => setTimeout(r, 800));
      onComplete({
        newNotebook: mode === 'new' ? (newName.trim() || 'My Notebook') : null,
        notebookId: nbId,
        files,
        result,
      });
    } catch (e) {
      setStep(-1);
      setError(e.response?.data?.detail || e.message || 'Upload failed');
    }
  };

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && step < 0 && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <span className="modal-title">
            {mode === 'new' ? 'Create New Notebook' : `Add Documents to ${notebookName || 'Notebook'}`}
          </span>
          {step < 0 && (
            <button className="icon-btn" onClick={onClose}><Icon name="x" size={14}/></button>
          )}
        </div>

        {step < 0 ? (
          <>
            <div
              className={`drop-zone ${dragging ? 'dragging' : ''} ${files.length ? 'has-files' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
            >
              <input ref={inputRef} type="file" accept={accept} hidden multiple
                onChange={e => setFiles(Array.from(e.target.files).slice(0, 5))} />
              {files.length === 0 ? (
                <>
                  <Icon name="upload" size={32} stroke={1.5} style={{ color: 'var(--primary)', opacity: 0.8 }} />
                  <div className="drop-text">Drag files here or click to browse</div>
                  <div className="drop-hint">PDF · DOCX · XLSX · TXT · HTML</div>
                </>
              ) : (
                <div className="file-list">
                  {files.map((f, i) => (
                    <div key={i} className="file-row">
                      <Icon name="file" size={14}/>
                      <span className="file-name">{f.name}</span>
                      <span className="file-size">{(f.size / 1024).toFixed(0)} KB</span>
                      <button className="icon-btn" onClick={e => { e.stopPropagation(); setFiles(fs => fs.filter((_, j) => j !== i)); }}>
                        <Icon name="x" size={12}/>
                      </button>
                    </div>
                  ))}
                  <div className="drop-hint" style={{ marginTop: 8 }}>Click to add more files</div>
                </div>
              )}
            </div>

            {mode === 'new' && (
              <div className="modal-field">
                <label className="field-label">Notebook name</label>
                <input className="field-input" placeholder="e.g. Apple Earnings 2025"
                  value={newName} onChange={e => setNewName(e.target.value)} />
              </div>
            )}

            <div className="modal-toggle">
              <div className="toggle-info">
                <span className="toggle-label">Use RAPTOR hierarchical indexing</span>
                <span className="toggle-hint">Builds a summary tree for better thematic understanding</span>
              </div>
              <button className={`toggle-btn ${useRaptor ? 'on' : ''}`}
                onClick={() => setUseRaptor(v => !v)}>
                <span className="toggle-knob"/>
              </button>
            </div>

            {error && <div className="upload-error">{error}</div>}

            <div className="modal-actions">
              <button className="btn-ghost" onClick={onClose}>Cancel</button>
              <button className="btn-primary" onClick={handleUpload} disabled={!files.length}>
                <Icon name="upload" size={13}/> Upload &amp; Index
              </button>
            </div>
          </>
        ) : (
          <div className="upload-progress">
            {STEPS.map((label, i) => (
              <div key={i} className={`progress-step ${i < step ? 'done' : i === step ? 'active' : 'pending'}`}>
                <span className="ps-icon">
                  {i < step ? <Icon name="check" size={13} stroke={3}/> :
                   i === step ? <span className="ps-spinner"/> : '○'}
                </span>
                <span className="ps-label">{label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
