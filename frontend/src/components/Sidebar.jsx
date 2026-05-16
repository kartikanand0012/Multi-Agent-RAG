import React from 'react';
import Icon from './Icons';

export default function Sidebar({ notebooks, activeId, route, onSelect, onNewNotebook, onDeleteNotebook, onGotoSettings, onGotoHome }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo" onClick={onGotoHome} style={{ cursor: 'pointer' }}>
        <div className="logo-icon">R</div>
        <span className="logo-text">RAG Studio</span>
      </div>

      <button className="btn-primary sidebar-new" onClick={onNewNotebook}>
        <Icon name="plus" size={14} /> New Notebook
      </button>

      <div className="sidebar-notebooks">
        {notebooks.map(nb => (
          <div
            key={nb.id}
            className={`nb-item ${activeId === nb.id && route === 'notebook' ? 'active' : ''}`}
            onClick={() => onSelect(nb.id)}
          >
            <div className="nb-item-main">
              <div className="nb-name">{nb.name}</div>
              <div className="nb-meta">
                <span className="nb-badge">{nb.docCount} docs</span>
                <span className="nb-time">{nb.lastQueried}</span>
              </div>
            </div>
            <button
              className="nb-delete icon-btn"
              onClick={e => { e.stopPropagation(); onDeleteNotebook(nb.id); }}
              title="Delete notebook"
            >
              <Icon name="trash" size={13} />
            </button>
          </div>
        ))}
        {notebooks.length === 0 && (
          <div className="nb-empty">No notebooks yet</div>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="health-dot" title="System healthy" />
        <span className="health-text">All systems operational</span>
        <button className="icon-btn ml-auto" onClick={onGotoSettings} title="Settings">
          <Icon name="settings" size={15} />
        </button>
      </div>
    </aside>
  );
}
