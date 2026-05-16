// D3-style force-directed knowledge map — implemented in plain SVG with a tiny custom
// physics loop so we don't have to load d3. Same look + behavior described in spec.
const { useEffect, useRef, useState: useStateK, useMemo } = React;

function generateMap(seed = 1) {
  // 3 layer-2 (top summaries), ~7 layer-1 (clusters), ~24 layer-0 (chunks)
  const rand = (() => { let s = seed; return () => (s = (s*9301 + 49297) % 233280) / 233280; })();
  const nodes = [];
  const links = [];
  const l2Texts = [
    "Apple Q3 2024 financial performance overview",
    "Services and Wearables growth drivers",
    "Regional revenue distribution and outlook"
  ];
  const l1Texts = [
    "iPhone unit sales by quarter",
    "Services revenue: App Store, iCloud, AppleCare",
    "Mac and iPad segment trends",
    "Greater China revenue and FX impact",
    "AI initiatives and Apple Intelligence rollout",
    "Capex and R&D spending breakdown",
    "Guidance and forward-looking commentary"
  ];
  for (let i = 0; i < 3; i++) {
    nodes.push({ id: `l2-${i}`, layer: 2, text: l2Texts[i] });
  }
  for (let i = 0; i < 7; i++) {
    const parent = `l2-${i % 3}`;
    nodes.push({ id: `l1-${i}`, layer: 1, text: l1Texts[i], parent });
    links.push({ source: parent, target: `l1-${i}` });
  }
  for (let i = 0; i < 24; i++) {
    const parent = `l1-${i % 7}`;
    nodes.push({
      id: `l0-${i}`,
      layer: 0,
      text: `Chunk ${i}: "...quarterly results reflected continued strength in Services with revenue growth of 14% year-over-year..."`,
      parent,
    });
    links.push({ source: parent, target: `l0-${i}` });
  }
  return { nodes, links };
}

function KnowledgeMap() {
  const wrapRef = useRef(null);
  const svgRef = useRef(null);
  const [hover, setHover] = useStateK(null);
  const [selected, setSelected] = useStateK(null);
  const data = useMemo(() => generateMap(7), []);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;

    // initial positions: layered radial
    const ns = data.nodes.map(n => ({
      ...n,
      x: w/2 + (Math.random() - 0.5) * 100,
      y: h/2 + (Math.random() - 0.5) * 100,
      vx: 0, vy: 0,
    }));
    const byId = Object.fromEntries(ns.map(n => [n.id, n]));
    const ls = data.links.map(l => ({ source: byId[l.source], target: byId[l.target] }));

    let alpha = 1;
    let raf;
    const tick = () => {
      // repulsion (small N — O(n²) is fine)
      for (let i = 0; i < ns.length; i++) {
        for (let j = i+1; j < ns.length; j++) {
          const a = ns[i], b = ns[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx*dx + dy*dy + 0.01;
          let d = Math.sqrt(d2);
          const strength = 1400 / d2;
          const fx = (dx/d) * strength;
          const fy = (dy/d) * strength;
          a.vx -= fx; a.vy -= fy;
          b.vx += fx; b.vy += fy;
        }
      }
      // link springs
      for (const l of ls) {
        const dx = l.target.x - l.source.x;
        const dy = l.target.y - l.source.y;
        const d = Math.sqrt(dx*dx + dy*dy) || 0.01;
        const target = 55;
        const f = (d - target) * 0.04;
        const fx = (dx/d) * f;
        const fy = (dy/d) * f;
        l.source.vx += fx; l.source.vy += fy;
        l.target.vx -= fx; l.target.vy -= fy;
      }
      // gentle gravity to center
      const cx = w/2, cy = h/2;
      for (const n of ns) {
        n.vx += (cx - n.x) * 0.005;
        n.vy += (cy - n.y) * 0.005;
        n.vx *= 0.78;
        n.vy *= 0.78;
        n.x += n.vx * alpha;
        n.y += n.vy * alpha;
        // soft bounds
        n.x = Math.max(20, Math.min(w-20, n.x));
        n.y = Math.max(20, Math.min(h-20, n.y));
      }
      alpha *= 0.992;
      if (alpha > 0.02) alpha += 0.001 * Math.sin(Date.now()/1200); // tiny float
      paint();
      raf = requestAnimationFrame(tick);
    };

    const paint = () => {
      const svg = svgRef.current;
      if (!svg) return;
      // update line/circle positions
      svg.querySelectorAll('line[data-id]').forEach((el) => {
        const [s, t] = el.getAttribute('data-id').split('|');
        const a = byId[s], b = byId[t];
        if (a && b) {
          el.setAttribute('x1', a.x); el.setAttribute('y1', a.y);
          el.setAttribute('x2', b.x); el.setAttribute('y2', b.y);
        }
      });
      svg.querySelectorAll('circle[data-id]').forEach((el) => {
        const n = byId[el.getAttribute('data-id')];
        if (n) {
          el.setAttribute('cx', n.x);
          el.setAttribute('cy', n.y);
        }
      });
    };

    // warmup
    for (let i = 0; i < 60; i++) {
      // skip render
      // mimic tick body without rAF
      for (let a = 0; a < ns.length; a++) for (let b = a+1; b < ns.length; b++) {
        const A = ns[a], B = ns[b];
        let dx = B.x - A.x, dy = B.y - A.y;
        let d2 = dx*dx + dy*dy + 0.01;
        let d = Math.sqrt(d2);
        const s = 1400 / d2;
        const fx = (dx/d)*s, fy = (dy/d)*s;
        A.vx -= fx; A.vy -= fy;
        B.vx += fx; B.vy += fy;
      }
      for (const l of ls) {
        const dx = l.target.x - l.source.x;
        const dy = l.target.y - l.source.y;
        const d = Math.sqrt(dx*dx + dy*dy) || 0.01;
        const f = (d - 55) * 0.04;
        const fx = (dx/d) * f, fy = (dy/d) * f;
        l.source.vx += fx; l.source.vy += fy;
        l.target.vx -= fx; l.target.vy -= fy;
      }
      for (const n of ns) {
        n.vx += (w/2 - n.x) * 0.005;
        n.vy += (h/2 - n.y) * 0.005;
        n.vx *= 0.78; n.vy *= 0.78;
        n.x += n.vx; n.y += n.vy;
      }
    }
    // store and start animation
    KnowledgeMap._ns = ns;
    KnowledgeMap._byId = byId;
    paint();
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [data]);

  const layerStyle = (layer) => {
    if (layer === 2) return { r: 14, fill: '#6C63FF', stroke: '#8a83ff' };
    if (layer === 1) return { r: 10, fill: '#00D4AA', stroke: '#33e0bb' };
    return { r: 4, fill: '#5b607a', stroke: '#8B90A7' };
  };

  // subtree highlight set
  const highlightSet = useMemo(() => {
    if (!selected) return null;
    const set = new Set([selected]);
    const findChildren = (id) => {
      for (const l of data.links) {
        if (l.source === id) {
          set.add(l.target);
          findChildren(l.target);
        }
      }
    };
    findChildren(selected);
    // also include parents
    let cur = selected;
    while (true) {
      const p = data.nodes.find(n => n.id === cur)?.parent;
      if (!p) break;
      set.add(p);
      cur = p;
    }
    return set;
  }, [selected, data]);

  const hoverNode = hover && (KnowledgeMap._byId?.[hover] || data.nodes.find(n => n.id === hover));
  const dim = (id) => highlightSet && !highlightSet.has(id);

  return (
    <div className="km-wrap" ref={wrapRef} onClick={() => setSelected(null)}>
      <svg ref={svgRef}>
        <defs>
          <radialGradient id="bg-fade" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(108,99,255,0.08)"/>
            <stop offset="100%" stopColor="transparent"/>
          </radialGradient>
        </defs>
        <rect width="100%" height="100%" fill="url(#bg-fade)"/>
        {data.links.map((l, i) => (
          <line
            key={i}
            data-id={`${l.source}|${l.target}`}
            stroke={dim(l.source) || dim(l.target) ? "rgba(45,49,73,0.3)" : "rgba(139,144,167,0.35)"}
            strokeWidth="1"
          />
        ))}
        {data.nodes.map((n) => {
          const s = layerStyle(n.layer);
          const isDim = dim(n.id);
          const isSel = selected === n.id;
          return (
            <g key={n.id}>
              <circle
                data-id={n.id}
                r={s.r + (isSel ? 4 : 0)}
                fill={s.fill}
                opacity={isDim ? 0.18 : 1}
                stroke={s.stroke}
                strokeOpacity={isDim ? 0.2 : 0.5}
                strokeWidth="1.5"
                style={{ cursor: 'pointer', transition: 'opacity 0.25s, r 0.2s' }}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                onClick={(e) => { e.stopPropagation(); setSelected(selected === n.id ? null : n.id); }}
              />
            </g>
          );
        })}
      </svg>

      {hoverNode && (
        <div className="km-tooltip" style={{
          left: Math.min((hoverNode.x || 0) + 16, (wrapRef.current?.clientWidth || 999) - 240),
          top: Math.max((hoverNode.y || 0) - 10, 10),
        }}>
          <div style={{color: hoverNode.layer===2?'#8a83ff':hoverNode.layer===1?'#33e0bb':'var(--text-2)', fontSize:10, marginBottom:4, fontWeight:600}}>
            LAYER {hoverNode.layer} {hoverNode.layer===2?'· Top Summary':hoverNode.layer===1?'· Cluster':'· Leaf Chunk'}
          </div>
          {hoverNode.text?.slice(0, 120)}{hoverNode.text?.length > 120 ? '…' : ''}
        </div>
      )}

      <div className="km-zoom">
        <button className="km-btn" title="Zoom to fit">
          <Icon name="zoomFit" size={11}/> Fit
        </button>
      </div>
      <div className="km-legend">
        <div className="km-legend-row"><span className="km-legend-dot" style={{background:'#6C63FF'}}></span> L2 · Summaries · 3</div>
        <div className="km-legend-row"><span className="km-legend-dot" style={{background:'#00D4AA'}}></span> L1 · Clusters · 7</div>
        <div className="km-legend-row"><span className="km-legend-dot" style={{background:'#8B90A7'}}></span> L0 · Chunks · 24</div>
      </div>
    </div>
  );
}

window.KnowledgeMap = KnowledgeMap;
