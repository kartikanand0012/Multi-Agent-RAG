import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import Icon from './Icons';

export default function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen]  = useState(false);

  if (!user) return null;
  const { profile, stats } = user;

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
