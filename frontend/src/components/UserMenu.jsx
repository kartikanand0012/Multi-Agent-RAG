import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import Icon from './Icons';

// Pure helper — computes the human-readable countdown given a reference "now".
// Kept outside the component so it doesn't depend on render-time impurities.
function formatResetIn(iso, nowMs) {
  if (!iso) return null;
  const diffMs = new Date(iso).getTime() - nowMs;
  if (diffMs <= 0) return 'resets soon';
  const totalMin = Math.floor(diffMs / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `resets in ${h}h ${m}m` : `resets in ${m}m`;
}

export default function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen]  = useState(false);
  const [nowMs, setNowMs] = useState(null);   // set in effect — keeps render pure

  // Tick "now" only while the dropdown is open. Avoids the
  // react-hooks/purity lint error from calling Date.now() during render.
  useEffect(() => {
    if (!open) { setNowMs(null); return; }
    setNowMs(Date.now());
    const id = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(id);
  }, [open]);

  if (!user) return null;
  const { profile, stats, quota } = user;

  const queryPct = quota?.max_queries
    ? Math.min(100, Math.round((quota.used_queries / quota.max_queries) * 100))
    : 0;
  const resetIn = nowMs != null ? formatResetIn(quota?.resets_at, nowMs) : null;

  const initials = (profile.full_name || profile.username)
    .split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);

  return (
    <div className="user-menu" style={{ position: 'relative' }}>
      <button className="user-avatar-btn" onClick={() => setOpen(o => !o)} title={profile.username}>
        <span className="user-avatar">{initials}</span>
        <span className="user-name">{profile.full_name || profile.username}</span>
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={12}/>
      </button>

      {open && (
        <>
          <div className="user-menu-backdrop" onClick={() => setOpen(false)}/>
          <div className="user-menu-dropdown">
            <div className="um-header">
              <span className="um-avatar">{initials}</span>
              <div>
                <div className="um-name">{profile.full_name || profile.username}</div>
                <div className="um-email">{profile.email}</div>
              </div>
            </div>

            <div className="um-stats">
              <div className="um-stat"><span>{stats.queries_this_month}</span><span>queries this month</span></div>
              <div className="um-stat"><span>{stats.notebooks_count}</span><span>notebooks</span></div>
              <div className="um-stat"><span>{stats.total_uploads}</span><span>uploads total</span></div>
            </div>

            {quota && (
              <div className="um-quota">
                <div className="um-quota-head">
                  <span>Daily quota</span>
                  <span className="um-quota-count">{quota.used_queries} / {quota.max_queries}</span>
                </div>
                <div className="um-quota-bar"><div className="um-quota-fill" style={{ width: `${queryPct}%` }}/></div>
                {resetIn && (
                  <div className="um-quota-foot">{resetIn}</div>
                )}
              </div>
            )}

            {profile.is_admin && (
              <div className="um-badge-admin">Admin</div>
            )}

            <div className="um-divider"/>

            <button className="um-item" onClick={() => { setOpen(false); logout(); }}>
              <Icon name="x" size={14}/> Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
