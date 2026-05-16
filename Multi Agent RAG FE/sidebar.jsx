// Sidebar with notebook list, system health, settings access
const { useState } = React;

function Sidebar({ notebooks, activeId, route, onSelect, onNewNotebook, onDeleteNotebook, onGotoSettings, onGotoHome }) {
  return (
    <aside className="sidebar">
      <button className="sb-logo" onClick={onGotoHome} style={{cursor:'pointer'}}>
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
            <button className="nb-del" onClick={(e) => { e.stopPropagation(); onDeleteNotebook(nb.id); }} title="Delete notebook">
              <Icon name="trash" size={14}/>
            </button>
          </div>
        ))}
      </div>

      <div className="sb-footer">
        <div className="sys-health">
          <span className="sys-dot"></span>
          <span>All systems operational</span>
        </div>
        <div className="sb-bottom">
          <div className="sb-version">v1.0.0</div>
          <button
            className={"sb-gear " + (route === 'settings' ? 'active' : '')}
            onClick={onGotoSettings}
            title="Settings"
          >
            <Icon name="settings" size={16}/>
          </button>
        </div>
      </div>
    </aside>
  );
}

window.Sidebar = Sidebar;
