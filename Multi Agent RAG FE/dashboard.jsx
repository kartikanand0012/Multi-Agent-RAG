function Dashboard({ onNewNotebook }) {
  return (
    <div className="dash">
      <div className="dash-hero">
        <div className="dash-illus">
          <Icon name="sparkles" size={42} stroke={1.5}/>
        </div>
        <h1>Welcome to RAG Studio</h1>
        <p>Upload documents to create your first AI-powered notebook. Ask anything — four specialized agents handle the rest.</p>
      </div>

      <div className="dash-cards">
        <div className="dash-card primary" onClick={onNewNotebook}>
          <div className="dash-icon-wrap"><Icon name="upload" size={20}/></div>
          <div className="col" style={{gap:4}}>
            <div className="dash-card-title">Create Notebook</div>
            <div className="dash-card-sub">Drag in PDFs, spreadsheets, or docs and we'll index them with RAPTOR hierarchical retrieval.</div>
          </div>
          <button className="btn-primary" style={{alignSelf:'flex-start', marginTop:4}}>
            Get started <Icon name="arrowRight" size={14}/>
          </button>
        </div>

        <div className="dash-card">
          <div className="dash-icon-wrap" style={{background:'rgba(0,212,170,0.14)', color:'var(--secondary)'}}>
            <Icon name="layers" size={20}/>
          </div>
          <div className="col" style={{gap:4}}>
            <div className="dash-card-title">How it works</div>
            <div className="dash-card-sub">Every query routes through a four-agent pipeline with self-verifying citations.</div>
          </div>
          <div className="flow">
            {['Upload','Index','Ask','Validate'].map((label, i) => (
              <React.Fragment key={label}>
                <div className="flow-step">
                  <div className="flow-step-num">{i+1}</div>
                  <span>{label}</span>
                </div>
                {i < 3 && <span className="flow-arrow">→</span>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

window.Dashboard = Dashboard;
