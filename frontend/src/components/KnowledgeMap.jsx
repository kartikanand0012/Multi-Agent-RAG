import React, { useEffect, useRef, useState, useMemo } from 'react';
import { fetchMap } from '../services/api';

const LAYER = {
  2: { r: 20, fill: '#6C63FF', stroke: '#8a83ff', glow: 'glow2', label: 'Top Summary',      desc: 'Global document summary — highest abstraction level' },
  1: { r: 13, fill: '#00D4AA', stroke: '#00eebb', glow: 'glow1', label: 'Cluster Summary',   desc: 'Topic cluster summary — groups related leaf chunks' },
  0: { r: 4,  fill: '#5b607a', stroke: '#8B90A7', glow: '',      label: 'Leaf Chunk',         desc: 'Raw document chunk — original extracted text' },
};

const EDGE_REL = {
  '2-1': { dir: 'Parent → Child', label: 'Summarizes cluster', color: '#6C63FF' },
  '1-0': { dir: 'Parent → Child', label: 'Contains chunk',     color: '#00D4AA' },
  '1-2': { dir: 'Child → Parent', label: 'Part of summary',    color: '#6C63FF' },
  '0-1': { dir: 'Child → Parent', label: 'Belongs to cluster', color: '#00D4AA' },
};

const VW = 520, VH = 500;

function buildLayout(nodes, edges) {
  const pos = {};
  const cx = VW / 2, cy = VH / 2;
  const childParent = {};
  edges.forEach(e => { childParent[e.to] = e.from; });

  const l2 = nodes.filter(n => n.layer === 2);
  const l1 = nodes.filter(n => n.layer === 1);
  const l0 = nodes.filter(n => n.layer === 0);

  // L2 — centre
  const l2ring = l2.length <= 1 ? 0 : Math.min(40, 25 * l2.length / Math.PI);
  l2.forEach((n, i) => {
    const a = l2.length === 1 ? 0 : (i / l2.length) * 2 * Math.PI - Math.PI / 2;
    pos[n.id] = { x: cx + l2ring * Math.cos(a), y: cy + l2ring * Math.sin(a) };
  });

  // L1 — inner ring
  const l1r = Math.min(cx - 18, cy - 18, 155);
  l1.forEach((n, i) => {
    const a = (i / Math.max(l1.length, 1)) * 2 * Math.PI - Math.PI / 2;
    pos[n.id] = { x: cx + l1r * Math.cos(a), y: cy + l1r * Math.sin(a) };
  });

  // L0 — outer ring sorted by parent (siblings adjacent = visible grouping)
  const l1Idx = {};
  l1.forEach((n, i) => { l1Idx[n.id] = i; });
  const l0Sorted = [...l0].sort((a, b) =>
    (l1Idx[childParent[a.id]] ?? 9999) - (l1Idx[childParent[b.id]] ?? 9999)
  );
  const l0r = Math.min(cx - 5, cy - 5, 234);
  l0Sorted.forEach((n, i) => {
    const a = (i / Math.max(l0Sorted.length, 1)) * 2 * Math.PI - Math.PI / 2;
    pos[n.id] = { x: cx + l0r * Math.cos(a), y: cy + l0r * Math.sin(a) };
  });

  return pos;
}

export default function KnowledgeMap({ notebookId }) {
  const [data, setData]         = useState({ nodes: [], edges: [] });
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [selected, setSelected] = useState(null);   // node id
  const [selEdge, setSelEdge]   = useState(null);   // { from, to }
  const [xf, setXf]             = useState({ tx: 0, ty: 0, s: 1 });
  const [detailTab, setDetailTab] = useState('info'); // 'info' | 'children' | 'edge'
  const svgRef  = useRef(null);
  const wrapRef = useRef(null);
  const dragRef = useRef(null);

  useEffect(() => {
    if (!notebookId) return;
    setLoading(true); setError(null); setSelected(null); setSelEdge(null);
    fetchMap(notebookId)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [notebookId]);

  const pos     = useMemo(() => buildLayout(data.nodes || [], data.edges || []), [data]);
  const nodeMap = useMemo(() => Object.fromEntries((data.nodes || []).map(n => [n.id, n])), [data.nodes]);

  // adjacency: nodeId → Set of connected nodeIds
  const adj = useMemo(() => {
    const a = {};
    (data.edges || []).forEach(e => {
      if (!a[e.from]) a[e.from] = new Set();
      if (!a[e.to])   a[e.to]   = new Set();
      a[e.from].add(e.to);
      a[e.to].add(e.from);
    });
    return a;
  }, [data.edges]);

  // parent map: childId → parentId
  const parentMap = useMemo(() => {
    const pm = {};
    (data.edges || []).forEach(e => { pm[e.to] = e.from; });
    return pm;
  }, [data.edges]);

  // children map: parentId → [childIds]
  const childrenMap = useMemo(() => {
    const cm = {};
    (data.edges || []).forEach(e => {
      if (!cm[e.from]) cm[e.from] = [];
      cm[e.from].push(e.to);
    });
    return cm;
  }, [data.edges]);

  const selNode    = selected ? nodeMap[selected] : null;
  const neighbors  = selNode  ? (adj[selected] || new Set()) : null;
  const selEdgeFrom = selEdge ? nodeMap[selEdge.from] : null;
  const selEdgeTo   = selEdge ? nodeMap[selEdge.to]   : null;

  // ── Scroll-to-zoom (passive:false on wrapper div) ──────────────────────────
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const handler = e => {
      e.preventDefault();
      e.stopPropagation();
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const mx = (e.clientX - rect.left) * (VW / rect.width);
      const my = (e.clientY - rect.top)  * (VH / rect.height);
      const f  = e.deltaY < 0 ? 1.12 : 0.89;
      setXf(x => {
        const ns = Math.max(0.2, Math.min(7, x.s * f));
        const r  = ns / x.s;
        return { s: ns, tx: mx - (mx - x.tx) * r, ty: my - (my - x.ty) * r };
      });
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, []); // stable — uses refs only, functional setXf

  // ── Pan ────────────────────────────────────────────────────────────────────
  const onSvgDown = e => {
    const tag = e.target.tagName;
    if (tag === 'svg' || tag === 'line' || tag === 'g') {
      dragRef.current = { sx: e.clientX - xf.tx, sy: e.clientY - xf.ty };
    }
  };
  const onMove = e => {
    if (!dragRef.current) return;
    setXf(x => ({ ...x, tx: e.clientX - dragRef.current.sx, ty: e.clientY - dragRef.current.sy }));
  };
  const onUp = () => { dragRef.current = null; };

  // ── Clear selection when clicking background ───────────────────────────────
  const onSvgClick = e => {
    if (e.target.tagName !== 'circle') { setSelected(null); setSelEdge(null); }
  };

  // ── Guards ─────────────────────────────────────────────────────────────────
  if (loading) return <div className="map-state">Loading knowledge graph…</div>;
  if (error)   return <div className="map-state map-error">Error: {error}</div>;
  if (!data.nodes?.length) return <div className="map-state">No documents indexed yet.</div>;

  const counts = {};
  data.nodes.forEach(n => { counts[n.layer] = (counts[n.layer] || 0) + 1; });

  const hasDetail = !!selNode || !!selEdge;

  return (
    <div className="km-root">
      {/* ── SVG canvas ──────────────────────────────────────────────────────── */}
      <div className="km-wrap" ref={wrapRef}
        onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        <svg ref={svgRef} viewBox={`0 0 ${VW} ${VH}`} width="100%" height="100%"
          style={{ cursor: dragRef.current ? 'grabbing' : 'grab', display: 'block' }}
          onMouseDown={onSvgDown} onClick={onSvgClick}
        >
          <defs>
            <filter id="glow2" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="5" result="b"/>
              <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <filter id="glow1" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="3.5" result="b"/>
              <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>

          <g transform={`translate(${xf.tx} ${xf.ty}) scale(${xf.s})`}>
            {/* ── Edges ── */}
            {(data.edges || []).map((edge, i) => {
              const a = pos[edge.from], b = pos[edge.to];
              if (!a || !b) return null;

              const fromLayer   = nodeMap[edge.from]?.layer ?? 1;
              const isL2toL1    = fromLayer === 2;
              const isEdgeSel   = selEdge && selEdge.from === edge.from && selEdge.to === edge.to;
              const isNodeTouch = selected && (edge.from === selected || edge.to === selected);

              if (!isL2toL1 && !isEdgeSel && !isNodeTouch) return null;

              const color = isEdgeSel ? '#FFB547' : isNodeTouch ? '#6C63FF' : 'rgba(108,99,255,0.35)';
              const sw    = isEdgeSel ? 2.5 : isNodeTouch ? 1.8 : 1.2;

              return (
                <g key={i} style={{ cursor: 'pointer' }}
                  onClick={e => {
                    e.stopPropagation();
                    setSelEdge({ from: edge.from, to: edge.to });
                    setSelected(null);
                    setDetailTab('edge');
                  }}
                >
                  {/* visible line */}
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={color} strokeWidth={sw}
                    strokeDasharray={isL2toL1 ? '' : '4 3'}
                    opacity={isEdgeSel ? 1 : 0.65}
                  />
                  {/* wider invisible hit-area */}
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke="transparent" strokeWidth={14}
                  />
                </g>
              );
            })}

            {/* ── Nodes (L0 → L1 → L2 so higher layers render on top) ── */}
            {[0, 1, 2].flatMap(layer =>
              (data.nodes || [])
                .filter(n => n.layer === layer)
                .map(n => {
                  const p = pos[n.id];
                  if (!p) return null;
                  const cfg        = LAYER[n.layer];
                  const isSel      = n.id === selected;
                  const isNbr      = neighbors?.has(n.id);
                  const isEdgePeer = selEdge && (n.id === selEdge.from || n.id === selEdge.to);
                  const isDim      = (selected || selEdge) && !isSel && !isNbr && !isEdgePeer;

                  return (
                    <circle key={n.id}
                      cx={p.x} cy={p.y}
                      r={cfg.r + (isSel || isEdgePeer ? 4 : 0)}
                      fill={cfg.fill}
                      fillOpacity={isDim ? 0.1 : isSel || isEdgePeer ? 1 : isNbr ? 0.95 : layer === 0 ? 0.55 : 0.8}
                      stroke={isSel || isEdgePeer ? '#fff' : isNbr ? cfg.stroke : cfg.fill}
                      strokeWidth={isSel || isEdgePeer ? 2.5 : isNbr ? 2 : layer > 0 ? 1.5 : 0}
                      filter={cfg.glow ? `url(#${cfg.glow})` : ''}
                      style={{ cursor: 'pointer', transition: 'all .15s ease' }}
                      onClick={e => {
                        e.stopPropagation();
                        setSelEdge(null);
                        setSelected(n.id === selected ? null : n.id);
                        setDetailTab('info');
                      }}
                    />
                  );
                })
            )}
          </g>
        </svg>

        {/* ── Zoom controls ── */}
        <div className="km-controls">
          <button className="km-btn" title="Zoom in"    onClick={() => setXf(x => ({ ...x, s: Math.min(7, x.s * 1.25) }))}>+</button>
          <button className="km-btn" title="Reset view" onClick={() => setXf({ tx: 0, ty: 0, s: 1 })}>⊙</button>
          <button className="km-btn" title="Zoom out"   onClick={() => setXf(x => ({ ...x, s: Math.max(0.2, x.s * 0.8) }))}>−</button>
        </div>

        {/* ── Legend ── */}
        <div className="km-legend">
          {[2, 1, 0].map(l => (
            <div key={l} className="km-legend-row">
              <span className="km-legend-dot" style={{ background: LAYER[l].fill }}/>
              <span>{LAYER[l].label} <strong>{counts[l] || 0}</strong></span>
            </div>
          ))}
          <div className="km-legend-hint">scroll · drag · click node/edge</div>
        </div>
      </div>

      {/* ── Detail panel ── */}
      {hasDetail && (
        <div className="km-detail">
          {/* Tab strip if node selected */}
          {selNode && (
            <div className="km-detail-tabs">
              {['info', 'children'].map(t => (
                <button key={t} className={`km-dtab ${detailTab === t ? 'active' : ''}`}
                  onClick={() => setDetailTab(t)}>
                  {t === 'info' ? 'Node Info' : `Connections (${(childrenMap[selected] || []).length + (parentMap[selected] ? 1 : 0)})`}
                </button>
              ))}
              <button className="km-detail-x" onClick={() => { setSelected(null); setSelEdge(null); }}>✕</button>
            </div>
          )}

          {/* Edge header */}
          {selEdge && (
            <div className="km-detail-tabs">
              <span className="km-dtab active">Edge Info</span>
              <button className="km-detail-x" onClick={() => setSelEdge(null)}>✕</button>
            </div>
          )}

          {/* ── Node Info tab ── */}
          {selNode && detailTab === 'info' && (
            <div className="km-detail-body">
              <div className="km-detail-head">
                <span className="km-detail-badge" style={{
                  background: LAYER[selNode.layer].fill + '22',
                  color: LAYER[selNode.layer].fill,
                  border: `1px solid ${LAYER[selNode.layer].fill}44`,
                }}>
                  L{selNode.layer} · {LAYER[selNode.layer].label}
                </span>
                {neighbors?.size > 0 && (
                  <span className="km-detail-conn">{neighbors.size} edge{neighbors.size !== 1 ? 's' : ''}</span>
                )}
              </div>
              <div className="km-detail-desc">{LAYER[selNode.layer].desc}</div>
              {selNode.source && (
                <div className="km-detail-src">
                  <span className="km-detail-src-label">Source</span>
                  <span className="km-detail-src-name">{selNode.source.split(/[\\/]/).pop()}</span>
                </div>
              )}
              <div className="km-detail-text">{selNode.text}</div>
            </div>
          )}

          {/* ── Connections tab ── */}
          {selNode && detailTab === 'children' && (
            <div className="km-detail-body">
              {/* Parent */}
              {parentMap[selected] && nodeMap[parentMap[selected]] && (
                <div className="km-conn-section">
                  <div className="km-conn-label">
                    <span className="km-conn-arrow">↑</span> Parent node
                  </div>
                  <div className="km-conn-item"
                    style={{ borderColor: LAYER[nodeMap[parentMap[selected]].layer].fill + '55' }}
                    onClick={() => { setSelected(parentMap[selected]); setDetailTab('info'); }}>
                    <span className="km-conn-badge" style={{ background: LAYER[nodeMap[parentMap[selected]].layer].fill }}>
                      L{nodeMap[parentMap[selected]].layer}
                    </span>
                    <span className="km-conn-text">{nodeMap[parentMap[selected]].text?.slice(0, 90)}…</span>
                  </div>
                </div>
              )}
              {/* Children */}
              {(childrenMap[selected] || []).length > 0 && (
                <div className="km-conn-section">
                  <div className="km-conn-label">
                    <span className="km-conn-arrow">↓</span> {childrenMap[selected].length} child node{childrenMap[selected].length !== 1 ? 's' : ''}
                  </div>
                  <div className="km-conn-list">
                    {childrenMap[selected].slice(0, 6).map(cid => {
                      const cn = nodeMap[cid];
                      if (!cn) return null;
                      return (
                        <div key={cid} className="km-conn-item"
                          style={{ borderColor: LAYER[cn.layer].fill + '55' }}
                          onClick={() => { setSelected(cid); setDetailTab('info'); }}>
                          <span className="km-conn-badge" style={{ background: LAYER[cn.layer].fill }}>
                            L{cn.layer}
                          </span>
                          <span className="km-conn-text">{cn.text?.slice(0, 80)}…</span>
                        </div>
                      );
                    })}
                    {childrenMap[selected].length > 6 && (
                      <div className="km-conn-more">+ {childrenMap[selected].length - 6} more</div>
                    )}
                  </div>
                </div>
              )}
              {!parentMap[selected] && !(childrenMap[selected] || []).length && (
                <div className="km-conn-empty">No connections found</div>
              )}
            </div>
          )}

          {/* ── Edge Info ── */}
          {selEdge && selEdgeFrom && selEdgeTo && (() => {
            const key  = `${selEdgeFrom.layer}-${selEdgeTo.layer}`;
            const rel  = EDGE_REL[key] || { dir: 'Connected', label: 'Linked', color: '#8B90A7' };
            return (
              <div className="km-detail-body">
                <div className="km-edge-type" style={{ borderColor: rel.color + '44', color: rel.color }}>
                  {rel.dir} · <strong>{rel.label}</strong>
                </div>
                {/* From node */}
                <div className="km-conn-section">
                  <div className="km-conn-label">From</div>
                  <div className="km-conn-item"
                    style={{ borderColor: LAYER[selEdgeFrom.layer].fill + '55' }}
                    onClick={() => { setSelected(selEdge.from); setSelEdge(null); setDetailTab('info'); }}>
                    <span className="km-conn-badge" style={{ background: LAYER[selEdgeFrom.layer].fill }}>
                      L{selEdgeFrom.layer} · {LAYER[selEdgeFrom.layer].label}
                    </span>
                    <span className="km-conn-text">{selEdgeFrom.text?.slice(0, 90)}…</span>
                  </div>
                </div>
                {/* To node */}
                <div className="km-conn-section">
                  <div className="km-conn-label">To</div>
                  <div className="km-conn-item"
                    style={{ borderColor: LAYER[selEdgeTo.layer].fill + '55' }}
                    onClick={() => { setSelected(selEdge.to); setSelEdge(null); setDetailTab('info'); }}>
                    <span className="km-conn-badge" style={{ background: LAYER[selEdgeTo.layer].fill }}>
                      L{selEdgeTo.layer} · {LAYER[selEdgeTo.layer].label}
                    </span>
                    <span className="km-conn-text">{selEdgeTo.text?.slice(0, 90)}…</span>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
