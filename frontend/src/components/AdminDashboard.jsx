import React, { useEffect, useState, useCallback } from 'react';
import Icon from './Icons';
import { adminOverview, adminUsers, adminUpdateQuota } from '../services/api';

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, color = 'var(--accent)' }) {
  return (
    <div className="cfg-card" style={{ gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}22`, color, display: 'grid', placeItems: 'center' }}>
          <Icon name={icon} size={15}/>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1 }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{sub}</div>}
    </div>
  );
}

// ── Quota editor ──────────────────────────────────────────────────────────────
function QuotaEditor({ user, onSaved }) {
  const [val, setVal] = useState(user.max_queries ?? 200);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      await adminUpdateQuota(user.id, Number(val));
      onSaved(user.id, Number(val));
    } catch (e) {
      setErr(e.response?.data?.detail || 'Failed');
    } finally { setSaving(false); }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <input
        type="number" min={0} max={10000}
        value={val} onChange={e => setVal(e.target.value)}
        style={{ width: 70, padding: '3px 6px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 13 }}
      />
      <button className="btn-primary" style={{ padding: '3px 10px', fontSize: 12 }} onClick={save} disabled={saving}>
        {saving ? '…' : 'Save'}
      </button>
      {err && <span style={{ color: 'var(--danger)', fontSize: 11 }}>{err}</span>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AdminDashboard() {
  const [overview, setOverview]   = useState(null);
  const [users, setUsers]         = useState([]);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(0);
  const [loadingOv, setLoadingOv] = useState(true);
  const [loadingU, setLoadingU]   = useState(true);
  const [editingId, setEditingId] = useState(null);
  const PAGE = 20;

  useEffect(() => {
    adminOverview()
      .then(setOverview)
      .catch(() => {})
      .finally(() => setLoadingOv(false));
  }, []);

  const loadUsers = useCallback((p = 0) => {
    setLoadingU(true);
    adminUsers(PAGE, p * PAGE)
      .then(data => { setUsers(data.users ?? data.items ?? []); setTotal(data.total ?? 0); })
      .catch(() => {})
      .finally(() => setLoadingU(false));
  }, []);

  useEffect(() => { loadUsers(page); }, [page, loadUsers]);

  const handleQuotaSaved = (userId, newMax) => {
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, max_queries: newMax } : u));
    setEditingId(null);
  };

  return (
    <div className="settings">
      <h1>Admin Dashboard</h1>
      <p className="sub">System overview, user management, and quota controls.</p>

      {/* ── Overview stats ── */}
      <div className="section">
        <h3 className="section-h">Overview</h3>
        {loadingOv ? (
          <div style={{ color: 'var(--text-2)', fontSize: 14 }}>Loading…</div>
        ) : overview ? (
          <div className="cfg-grid">
            <StatCard icon="users"    label="Total users"         value={overview.users?.total}              color="var(--accent)"/>
            <StatCard icon="activity" label="Queries today"       value={overview.queries?.today}            color="var(--secondary)"/>
            <StatCard icon="activity" label="Queries this week"   value={overview.queries?.week}             sub={`${overview.queries?.month ?? 0} this month`} color="var(--secondary)"/>
            <StatCard icon="upload"   label="Uploads total"       value={overview.uploads?.total}            color="#a78bfa"/>
            <StatCard icon="layers"   label="Active notebooks"    value={overview.notebooks?.total}          color="#f59e0b"/>
            <StatCard icon="bolt"     label="Open alerts"         value={overview.alerts?.open ?? 0}         color="var(--danger)"/>
          </div>
        ) : (
          <div style={{ color: 'var(--danger)', fontSize: 13 }}>Could not load overview.</div>
        )}
      </div>

      {/* ── User list ── */}
      <div className="section">
        <h3 className="section-h">Users <span style={{ fontWeight: 400, color: 'var(--text-2)', fontSize: 13 }}>({total} total)</span></h3>

        <div className="table-card">
          <div className="table-row head" style={{ gridTemplateColumns: '1fr 1fr 80px 80px 160px 60px' }}>
            <div>Email</div>
            <div>Username</div>
            <div>Queries</div>
            <div>Uploads</div>
            <div>Daily quota</div>
            <div>Role</div>
          </div>

          {loadingU ? (
            <div className="table-row" style={{ justifyContent: 'center', color: 'var(--text-2)', fontSize: 13 }}>Loading…</div>
          ) : users.length === 0 ? (
            <div className="table-row" style={{ justifyContent: 'center', color: 'var(--text-2)', fontSize: 13 }}>No users found.</div>
          ) : users.map(u => (
            <div key={u.id} className="table-row" style={{ gridTemplateColumns: '1fr 1fr 80px 80px 160px 60px', alignItems: 'center' }}>
              <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.email}</div>
              <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{u.username}</div>
              <div style={{ fontSize: 13 }}>{u.total_queries ?? 0}</div>
              <div style={{ fontSize: 13 }}>{u.total_uploads ?? 0}</div>
              <div>
                {editingId === u.id ? (
                  <QuotaEditor user={u} onSaved={handleQuotaSaved}/>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 13 }}>{u.used_queries ?? 0} / {u.max_queries ?? 200}</span>
                    <button
                      className="btn-ghost"
                      style={{ padding: '2px 8px', fontSize: 11 }}
                      onClick={() => setEditingId(u.id)}
                    >
                      Edit
                    </button>
                  </div>
                )}
              </div>
              <div>
                {u.is_admin
                  ? <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: 'var(--accent)22', color: 'var(--accent)', fontWeight: 600 }}>Admin</span>
                  : <span style={{ fontSize: 11, color: 'var(--text-2)' }}>User</span>
                }
              </div>
            </div>
          ))}
        </div>

        {/* Pagination */}
        {total > PAGE && (
          <div style={{ display: 'flex', gap: 8, marginTop: 12, justifyContent: 'flex-end', alignItems: 'center' }}>
            <button className="btn-ghost" style={{ padding: '4px 12px' }} disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Page {page + 1} of {Math.ceil(total / PAGE)}</span>
            <button className="btn-ghost" style={{ padding: '4px 12px' }} disabled={(page + 1) * PAGE >= total} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        )}
      </div>
    </div>
  );
}
