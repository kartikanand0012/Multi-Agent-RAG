import React from 'react';
import Icon from './Icons';

export default function Dashboard({ onNewNotebook }) {
  return (
    <div className="dashboard">
      <div className="dash-center">
        <div className="dash-logo">R</div>
        <h1 className="dash-heading">Welcome to RAG Studio</h1>
        <p className="dash-sub">Upload documents to create your first AI-powered notebook</p>
        <div className="dash-cards">
          <div className="dash-card primary-card" onClick={onNewNotebook}>
            <Icon name="upload" size={28} stroke={1.5}/>
            <div className="dash-card-title">Create Notebook</div>
            <div className="dash-card-hint">Upload PDFs, DOCX, Excel, or text files</div>
          </div>
          <div className="dash-card">
            <Icon name="zap" size={28} stroke={1.5}/>
            <div className="dash-card-title">How it works</div>
            <div className="dash-steps">
              {['Upload documents', 'RAPTOR indexing', 'Ask questions', 'Agents validate'].map((s, i) => (
                <div key={i} className="dash-step">
                  <span className="dash-step-num">{i + 1}</span>
                  <span>{s}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
