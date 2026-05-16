import React, { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import AuthPage from './components/AuthPage';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import NotebookView from './components/NotebookView';
import Settings from './components/Settings';
import UploadModal from './components/UploadModal';
import Icon from './components/Icons';
import { createNotebook, deleteNotebook, fetchNotebooks } from './services/api';

// ── Inner app (requires auth) ─────────────────────────────────────────────────
function AppInner() {
  const { user, logout } = useAuth();
  const [notebooks, setNotebooks] = useState([]);
  const [activeId, setActiveId]   = useState(null);
  const [route, setRoute]         = useState('home');
  const [modal, setModal]         = useState(null);
  const [nbLoading, setNbLoading] = useState(true);

  // Load notebooks from server
  useEffect(() => {
    setNbLoading(true);
    fetchNotebooks()
      .then(nbs => {
        const mapped = nbs.map(n => ({
          id:          n.id,
          name:        n.name,
          docCount:    n.doc_count,
          lastQueried: new Date(n.updated_at).toLocaleDateString(),
        }));
        setNotebooks(mapped);
        if (mapped.length && !activeId) {
          setActiveId(mapped[0].id);
          setRoute('notebook');
        }
      })
      .catch(() => {})
      .finally(() => setNbLoading(false));
  }, [user]);

  const activeNotebook = notebooks.find(n => n.id === activeId);

  const handleSelect = id => { setActiveId(id); setRoute('notebook'); };

  const handleDelete = async id => {
    try { await deleteNotebook(id); } catch {}
    const next = notebooks.filter(n => n.id !== id);
    setNotebooks(next);
    if (activeId === id) {
      setActiveId(next[0]?.id || null);
      setRoute(next.length ? 'notebook' : 'home');
    }
  };

  const handleModalComplete = async res => {
    if (res.newNotebook) {
      try {
        const nb = await createNotebook(res.notebookId, res.newNotebook);
        const mapped = { id: nb.id, name: nb.name, docCount: res.files.length, lastQueried: 'just now' };
        setNotebooks(prev => [mapped, ...prev]);
        setActiveId(nb.id);
        setRoute('notebook');
      } catch {}
    } else if (activeNotebook) {
      setNotebooks(prev => prev.map(n =>
        n.id === activeNotebook.id ? { ...n, docCount: n.docCount + res.files.length, lastQueried: 'just now' } : n
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
        {route === 'settings' && (
          <Settings onClearAll={async () => {
            for (const nb of notebooks) {
              try { await deleteNotebook(nb.id); } catch {}
            }
            setNotebooks([]); setActiveId(null); setRoute('home');
          }}/>
        )}
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

// ── Root (handles auth gate) ──────────────────────────────────────────────────
function AppRoot() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg)' }}>
        <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }}/>
      </div>
    );
  }

  if (!user) return <AuthPage/>;
  return <AppInner/>;
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoot/>
    </AuthProvider>
  );
}
