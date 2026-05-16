import React, { useEffect, useRef, useState, useMemo } from 'react';
import { fetchMap } from '../services/api';

const LAYER_CONFIG = {
  2: { r: 28, color: '#6C63FF', label: 'Top summaries' },
  1: { r: 18, color: '#00D4AA', label: 'Cluster summaries' },
  0: { r: 7,  color: '#8B90A7', label: 'Leaf chunks' },
};

function usePhysics(nodes, links, width, height) {
  const posRef = useRef({});

  return useMemo(() => {
    if (!nodes.length) return { positions: {}, edges: [] };
    const pos = {};
    const byId = {};

    // Initial positions — layer-2 at top, spiral outward per layer
    nodes.forEach((n, i) => {
      const layer = n.layer;
      const siblings = nodes.filter(x => x.layer === layer);
      const idx = siblings.indexOf(n);
      const angle = (idx / Math.max(siblings.length, 1)) * 2 * Math.PI;
      const radius = layer === 2 ? 60 : layer === 1 ? 150 : 240;
      pos[n.id] = {
        x: width / 2 + radius * Math.cos(angle),
        y: height / 2 + radius * Math.sin(angle),
      };
      byId[n.id] = n;
    });

    const edges = links
      .filter(l => pos[l.from] && pos[l.to])
      .map(l => ({ ...l, x1: pos[l.from].x, y1: pos[l.from].y, x2: pos[l.to].x, y2: pos[l.to].y }));

    return { positions: pos, edges };
  }, [nodes, links, width, height]);
}

export default function KnowledgeMap({ notebookId }) {
  const [data, setData] = useState({ nodes: [], edges: [] });
  const [hover, setHover] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const svgRef = useRef(null);
  const W = 340, H = 320;

  useEffect(() => {
    if (!notebookId) return;
    setLoading(true);
    setError(null);
    fetchMap(notebookId)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [notebookId]);

  const { positions, edges } = usePhysics(data.nodes || [], data.edges || [], W, H);

  if (loading) return <div className="map-state">Loading knowledge map…</div>;
  if (error)   return <div className="map-state map-error">Could not load map: {error}</div>;
  if (!data.nodes?.length) return <div className="map-state">No documents indexed yet.</div>;

  return (
    <div className="knowledge-map">
      <svg ref={svgRef} width="100%" viewBox={`0 0 ${W} ${H}`} className="map-svg">
        {edges.map((e, i) => (
          <line key={i} x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke="#2D3149" strokeWidth={1} />
        ))}
        {data.nodes.map(n => {
          const p = positions[n.id];
          if (!p) return null;
          const cfg = LAYER_CONFIG[n.layer] || LAYER_CONFIG[0];
          return (
            <g key={n.id}
              onMouseEnter={() => setHover(n)}
              onMouseLeave={() => setHover(null)}
              style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={cfg.r}
                fill={cfg.color} fillOpacity={hover?.id === n.id ? 1 : 0.7}
                stroke={cfg.color} strokeWidth={hover?.id === n.id ? 2 : 0} />
            </g>
          );
        })}
      </svg>

      {hover && (
        <div className="map-tooltip">
          <div className="map-tooltip-layer">Layer {hover.layer} · {LAYER_CONFIG[hover.layer]?.label}</div>
          <div className="map-tooltip-text">{hover.text}</div>
        </div>
      )}

      <div className="map-legend">
        {Object.entries(LAYER_CONFIG).reverse().map(([layer, cfg]) => (
          <div key={layer} className="legend-item">
            <span className="legend-dot" style={{ background: cfg.color }} />
            <span>{cfg.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
