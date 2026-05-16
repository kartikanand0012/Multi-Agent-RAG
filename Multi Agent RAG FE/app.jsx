const { useState: useStateA } = React;

const initialNotebooks = [
  { id: 'nb1', name: 'Apple Earnings 2024', docCount: 4, totalChunks: 128, lastQueried: '2m ago' },
  { id: 'nb2', name: 'Q3 Board Materials', docCount: 8, totalChunks: 312, lastQueried: '1h ago' },
  { id: 'nb3', name: 'Competitor Research', docCount: 11, totalChunks: 487, lastQueried: 'Yesterday' },
  { id: 'nb4', name: 'Engineering RFCs', docCount: 23, totalChunks: 921, lastQueried: '3d ago' },
  { id: 'nb5', name: 'Customer Interviews', docCount: 6, totalChunks: 198, lastQueried: 'Last week' },
];

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#6C63FF",
  "density": "comfortable",
  "showLightningOnce": true,
  "alwaysStreaming": false
}/*EDITMODE-END*/;

function App() {
  const [notebooks, setNotebooks] = useStateA(initialNotebooks);
  const [activeId, setActiveId] = useStateA('nb1');
  const [route, setRoute] = useStateA('notebook'); // 'home' | 'notebook' | 'settings'
  const [modal, setModal] = useStateA(null); // null | 'add' | 'new'
  const tweaks = window.useTweaks ? window.useTweaks(TWEAK_DEFAULTS) : [TWEAK_DEFAULTS, () => {}];
  const [t, setTweak] = tweaks;

  // apply accent css var
  React.useEffect(() => {
    document.documentElement.style.setProperty('--primary', t.accent);
    // recompute dim version
    const c = t.accent;
    document.documentElement.style.setProperty('--primary-dim', hexToRgba(c, 0.16));
  }, [t.accent]);

  React.useEffect(() => {
    document.body.classList.toggle('density-compact', t.density === 'compact');
  }, [t.density]);

  const activeNotebook = notebooks.find(n => n.id === activeId) || notebooks[0];

  const handleSelectNotebook = (id) => {
    setActiveId(id);
    setRoute('notebook');
  };
  const handleNewNotebook = () => setModal('new');
  const handleAddDocument = () => setModal('add');
  const handleDeleteNotebook = (id) => {
    setNotebooks(ns => ns.filter(n => n.id !== id));
    if (activeId === id) {
      const next = notebooks.find(n => n.id !== id);
      setActiveId(next?.id);
      setRoute(next ? 'notebook' : 'home');
    }
  };
  const handleModalComplete = (res) => {
    if (res.newNotebook) {
      const id = 'nb-' + Date.now();
      const nb = { id, name: res.newNotebook, docCount: res.files.length, totalChunks: 32, lastQueried: 'just now' };
      setNotebooks(ns => [nb, ...ns]);
      setActiveId(id);
      setRoute('notebook');
    } else if (activeNotebook) {
      // bump doc count
      setNotebooks(ns => ns.map(n => n.id === activeNotebook.id ? { ...n, docCount: n.docCount + res.files.length, lastQueried: 'just now' } : n));
    }
    setModal(null);
  };

  const TweaksPanel = window.TweaksPanel;
  const TweakSection = window.TweakSection;
  const TweakColor = window.TweakColor;
  const TweakRadio = window.TweakRadio;
  const TweakToggle = window.TweakToggle;
  const TweakButton = window.TweakButton;

  return (
    <div className="app">
      <Sidebar
        notebooks={notebooks}
        activeId={activeId}
        route={route}
        onSelect={handleSelectNotebook}
        onNewNotebook={handleNewNotebook}
        onDeleteNotebook={handleDeleteNotebook}
        onGotoSettings={() => setRoute('settings')}
        onGotoHome={() => setRoute('home')}
      />
      <div className="main">
        {route === 'home' && <Dashboard onNewNotebook={handleNewNotebook}/>}
        {route === 'notebook' && activeNotebook && (
          <NotebookView
            key={activeNotebook.id}
            notebook={activeNotebook}
            onAddDocument={handleAddDocument}
          />
        )}
        {route === 'notebook' && !activeNotebook && <Dashboard onNewNotebook={handleNewNotebook}/>}
        {route === 'settings' && <Settings onClearAll={() => { setNotebooks([]); setRoute('home'); }}/>}
      </div>

      {modal && (
        <UploadModal
          notebookName={activeNotebook?.name}
          mode={modal}
          onClose={() => setModal(null)}
          onComplete={handleModalComplete}
        />
      )}

      {/* Mobile tab bar */}
      <div className="mobile-tabbar">
        <button className={"mtb-btn " + (route==='home'?'active':'')} onClick={() => setRoute('home')}>
          <Icon name="home" size={18}/> Home
        </button>
        <button className={"mtb-btn " + (route==='notebook'?'active':'')} onClick={() => setRoute('notebook')}>
          <Icon name="book" size={18}/> Notebook
        </button>
        <button className="mtb-btn" onClick={handleNewNotebook}>
          <Icon name="plus" size={18}/> New
        </button>
        <button className={"mtb-btn " + (route==='settings'?'active':'')} onClick={() => setRoute('settings')}>
          <Icon name="settings" size={18}/> Settings
        </button>
      </div>

      {TweaksPanel && (
        <TweaksPanel title="Tweaks">
          <TweakSection title="Brand">
            <TweakColor
              t={t} setTweak={setTweak} k="accent" label="Accent"
              options={['#6C63FF', '#00D4AA', '#FF6B9D', '#FFB547']}
            />
          </TweakSection>
          <TweakSection title="Density">
            <TweakRadio
              t={t} setTweak={setTweak} k="density" label="Spacing"
              options={[{value:'comfortable', label:'Comfy'}, {value:'compact', label:'Compact'}]}
            />
          </TweakSection>
          <TweakSection title="Demo">
            <TweakButton onClick={handleNewNotebook}>Open upload modal</TweakButton>
            <TweakButton onClick={() => { setRoute('home'); }}>Show empty state</TweakButton>
            <TweakButton onClick={() => setRoute('settings')}>Show settings</TweakButton>
          </TweakSection>
        </TweaksPanel>
      )}
    </div>
  );
}

function hexToRgba(hex, a) {
  const m = hex.replace('#', '');
  const r = parseInt(m.slice(0,2), 16);
  const g = parseInt(m.slice(2,4), 16);
  const b = parseInt(m.slice(4,6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
