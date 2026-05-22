import React from 'react';
import Icon from './Icons';
import UserMenu from './UserMenu';
import { useAuth } from '../context/AuthContext';

export default function Sidebar({ notebooks, activeId, route, onSelect, onNewNotebook, onDeleteNotebook, onGotoSettings, onGotoHome, onGotoAdmin }) {
  const { user } = useAuth();
  const isAdmin = user?.profile?.is_admin;
  return (
    <aside className="sidebar">
      <button className="sb-logo" onClick={onGotoHome}>
        <div className="sb-logo-mark">
          <Icon name="sparkles" size={14} stroke={2.5}/>
        </div>
        <div className="sb-logo-text">
          <div className="sb-logo-name">RAG Studio</div>
          <div className="sb-logo-sub">Multi-Agent</div>
        </div>
      </button>

      <button className="btn-primary block" onClick={onNewNotebook}>
        <Icon name="plus" size={14}/>
        <span className="label-text">New Notebook</span>
      </button>

      <div className="sb-section-label">Notebooks</div>
      <div className="notebook-list">
        {notebooks.map(nb => (
          <div
            key={nb.id}
            className={"notebook-item " + (route === 'notebook' && activeId === nb.id ? 'active' : '')}
            onClick={() => onSelect(nb.id)}
          >
            <div className="nb-row1">
              <span className="nb-name">{nb.name}</span>
              <span className="nb-count">{nb.docCount}</span>
            </div>
            <div className="nb-time">{nb.lastQueried}</div>
            <button className="nb-del" onClick={e => { e.stopPropagation(); onDeleteNotebook(nb.id); }} title="Delete">
              <Icon name="trash" size={14}/>
            </button>
          </div>
        ))}
        {notebooks.length === 0 && (
          <div style={{ padding: '12px 8px', color: 'var(--text-2)', fontSize: 13 }}>No notebooks yet</div>
        )}
      </div>

      <div className="sb-footer">
        <UserMenu/>
        <div className="sb-bottom">
          <div className="sb-version">v2.0.0</div>
          {isAdmin && (
            <button className={"sb-gear " + (route === 'admin' ? 'active' : '')} onClick={onGotoAdmin} title="Admin">
              <Icon name="users" size={16}/>
            </button>
          )}
          <button className={"sb-gear " + (route === 'settings' ? 'active' : '')} onClick={onGotoSettings} title="Settings">
            <Icon name="settings" size={16}/>
          </button>
        </div>
      </div>
    </aside>
  );
}
