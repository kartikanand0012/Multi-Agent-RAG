import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import NotebookView from './components/NotebookView';
import Settings from './components/Settings';
import UploadModal from './components/UploadModal';
import Icon from './components/Icons';

// Persist notebooks in localStorage so they survive page refresh
const STORAGE_KEY = 'rag-studio-notebooks';
const loadNotebooks = () => {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
  catch { return []; }
};
const saveNotebooks = nbs => localStorage.setItem(STORAGE_KEY, JSON.stringify(nbs));

export default function App() {
  const [notebooks, setNotebooks] = useState(loadNotebooks);
  const [activeId, setActiveId] = useState(notebooks[0]?.id || null);
  const [route, setRoute] = useState(notebooks.length ? 'notebook' : 'home');
  const [modal, setModal] = useState(null);

  const update = nbs => { setNotebooks(nbs); saveNotebooks(nbs); };

  const activeNotebook = notebooks.find(n => n.id === activeId);

  const handleSelect = id => { setActiveId(id); setRoute('notebook'); };

  const handleDelete = id => {
    const next = notebooks.filter(n => n.id !== id);
    update(next);
    if (activeId === id) {
      setActiveId(next[0]?.id || null);
      setRoute(next.length ? 'notebook' : 'home');
    }
  };

  const handleModalComplete = res => {
    if (res.newNotebook) {
      const nb = {
        id: res.notebookId,
        name: res.newNotebook,
        docCount: res.files.length,
        lastQueried: 'just now',
      };
      const updated = [nb, ...notebooks];
      update(updated);
      setActiveId(nb.id);
      setRoute('notebook');
    } else if (activeNotebook) {
      update(notebooks.map(n =>
        n.id === activeNotebook.id
          ? { ...n, docCount: n.docCount + res.files.length, lastQueried: 'just now' }
          : n
      ));
    }
    setModal(null);
  };

  return (
    <div className="app">
      <Sidebar
        notebooks={notebooks}
        activeId={activeId}
        route={route}
        onSelect={handleSelect}
        onNewNotebook={() => setModal('new')}
        onDeleteNotebook={handleDelete}
        onGotoSettings={() => setRoute('settings')}
        onGotoHome={() => setRoute('home')}
      />

      <div className="main">
        {route === 'home' && <Dashboard onNewNotebook={() => setModal('new')}/>}
        {route === 'notebook' && activeNotebook && (
          <NotebookView
            key={activeNotebook.id}
            notebook={activeNotebook}
            onAddDocument={() => setModal('add')}
          />
        )}
        {route === 'notebook' && !activeNotebook && <Dashboard onNewNotebook={() => setModal('new')}/>}
        {route === 'settings' && <Settings onClearAll={() => { update([]); setActiveId(null); setRoute('home'); }}/>}
      </div>

      {/* Mobile tab bar */}
      <div className="mobile-tabbar">
        {[['home','Home'],['notebook','Notebook'],['settings','Settings']].map(([r, label]) => (
          <button key={r} className={`mtb-btn ${route === r ? 'active' : ''}`} onClick={() => setRoute(r)}>
            <Icon name={r} size={18}/> {label}
          </button>
        ))}
        <button className="mtb-btn" onClick={() => setModal('new')}>
          <Icon name="plus" size={18}/> New
        </button>
      </div>

      {modal && (
        <UploadModal
          notebookName={activeNotebook?.name}
          mode={modal}
          onClose={() => setModal(null)}
          onComplete={handleModalComplete}
        />
      )}
    </div>
  );
}
