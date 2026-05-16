import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import Icon from './Icons';

export default function AuthPage() {
  const { login, register } = useAuth();
  const [tab, setTab]       = useState('login');   // 'login' | 'register'
  const [busy, setBusy]     = useState(false);
  const [error, setError]   = useState('');

  // Login fields
  const [loginEmail, setLoginEmail]       = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Register fields
  const [regEmail, setRegEmail]         = useState('');
  const [regUsername, setRegUsername]   = useState('');
  const [regPassword, setRegPassword]   = useState('');
  const [regName, setRegName]           = useState('');

  const handleLogin = async e => {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      await login(loginEmail, loginPassword);
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your email and password.');
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async e => {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      await register(regEmail, regUsername, regPassword, regName);
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        {/* Logo */}
        <div className="auth-logo">
          <div className="auth-logo-mark">
            <Icon name="sparkles" size={22} stroke={2.5}/>
          </div>
          <div>
            <div className="auth-logo-name">RAG Studio</div>
            <div className="auth-logo-sub">Multi-Agent · Production</div>
          </div>
        </div>

        {/* Tabs */}
        <div className="auth-tabs">
          <button className={`auth-tab ${tab === 'login' ? 'active' : ''}`}    onClick={() => { setTab('login');    setError(''); }}>Sign in</button>
          <button className={`auth-tab ${tab === 'register' ? 'active' : ''}`} onClick={() => { setTab('register'); setError(''); }}>Create account</button>
        </div>

        {/* Login */}
        {tab === 'login' && (
          <form className="auth-form" onSubmit={handleLogin}>
            <div className="auth-field">
              <label>Email</label>
              <input type="email" value={loginEmail} onChange={e => setLoginEmail(e.target.value)}
                placeholder="you@example.com" required autoFocus/>
            </div>
            <div className="auth-field">
              <label>Password</label>
              <input type="password" value={loginPassword} onChange={e => setLoginPassword(e.target.value)}
                placeholder="Your password" required/>
            </div>
            {error && <div className="auth-error">{error}</div>}
            <button type="submit" className="btn-primary auth-submit" disabled={busy}>
              {busy ? <span className="spinner"/> : <><Icon name="send" size={14}/> Sign in</>}
            </button>
          </form>
        )}

        {/* Register */}
        {tab === 'register' && (
          <form className="auth-form" onSubmit={handleRegister}>
            <div className="auth-field">
              <label>Full name <span className="auth-optional">(optional)</span></label>
              <input type="text" value={regName} onChange={e => setRegName(e.target.value)}
                placeholder="Kartik Anand"/>
            </div>
            <div className="auth-field">
              <label>Username</label>
              <input type="text" value={regUsername} onChange={e => setRegUsername(e.target.value)}
                placeholder="kartik123" required pattern="[a-zA-Z0-9_\-]+" minLength={3}/>
              <span className="auth-hint">Letters, numbers, _ and - only</span>
            </div>
            <div className="auth-field">
              <label>Email</label>
              <input type="email" value={regEmail} onChange={e => setRegEmail(e.target.value)}
                placeholder="you@example.com" required/>
            </div>
            <div className="auth-field">
              <label>Password</label>
              <input type="password" value={regPassword} onChange={e => setRegPassword(e.target.value)}
                placeholder="Min 8 chars, at least 1 digit" required minLength={8}/>
            </div>
            {error && <div className="auth-error">{error}</div>}
            <button type="submit" className="btn-primary auth-submit" disabled={busy}>
              {busy ? <span className="spinner"/> : <><Icon name="sparkles" size={14}/> Create account</>}
            </button>
          </form>
        )}

        <div className="auth-footer">
          Built with FastAPI · React · RAPTOR · LangGraph
        </div>
      </div>
    </div>
  );
}
