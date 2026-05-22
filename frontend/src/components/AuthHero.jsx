import React, { useEffect, useRef } from 'react';

// Interactive particle constellation that gently follows the cursor.
// Pure Canvas 2D — zero dependencies, ~60fps, pauses when tab hidden.
export default function AuthHero() {
  const canvasRef = useRef(null);
  const rafRef    = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    let width = 0, height = 0;
    let particles = [];
    const mouse = { x: -9999, y: -9999, active: false };

    const PARTICLE_COUNT = 90;
    const CONNECT_DIST   = 110;
    const CURSOR_RADIUS  = 160;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width  = rect.width;
      height = rect.height;
      canvas.width  = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const seed = () => {
      particles = Array.from({ length: PARTICLE_COUNT }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        r: 1 + Math.random() * 1.6,
      }));
    };

    const step = () => {
      ctx.clearRect(0, 0, width, height);

      // Gradient backdrop
      const g = ctx.createRadialGradient(width * 0.5, height * 0.5, 50, width * 0.5, height * 0.5, Math.max(width, height));
      g.addColorStop(0, 'rgba(108, 99, 255, 0.18)');
      g.addColorStop(0.5, 'rgba(0, 212, 170, 0.06)');
      g.addColorStop(1, 'rgba(15, 17, 23, 0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, width, height);

      // Update particles
      for (const p of particles) {
        // Drift
        p.x += p.vx;
        p.y += p.vy;

        // Mouse attraction (subtle)
        if (mouse.active) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const dist = Math.hypot(dx, dy);
          if (dist < CURSOR_RADIUS && dist > 0.5) {
            const pull = (1 - dist / CURSOR_RADIUS) * 0.04;
            p.vx += (dx / dist) * pull;
            p.vy += (dy / dist) * pull;
          }
        }

        // Velocity damping
        p.vx *= 0.985;
        p.vy *= 0.985;

        // Wrap edges
        if (p.x < -10) p.x = width + 10;
        if (p.x > width + 10) p.x = -10;
        if (p.y < -10) p.y = height + 10;
        if (p.y > height + 10) p.y = -10;
      }

      // Connecting lines
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i], b = particles[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const dist = Math.hypot(dx, dy);
          if (dist < CONNECT_DIST) {
            const alpha = (1 - dist / CONNECT_DIST) * 0.35;
            ctx.strokeStyle = `rgba(180, 180, 255, ${alpha})`;
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      // Cursor-to-particle highlight lines
      if (mouse.active) {
        for (const p of particles) {
          const d = Math.hypot(mouse.x - p.x, mouse.y - p.y);
          if (d < CURSOR_RADIUS) {
            const alpha = (1 - d / CURSOR_RADIUS) * 0.7;
            ctx.strokeStyle = `rgba(108, 99, 255, ${alpha})`;
            ctx.lineWidth = 0.9;
            ctx.beginPath();
            ctx.moveTo(mouse.x, mouse.y);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
          }
        }
      }

      // Particles
      for (const p of particles) {
        ctx.fillStyle = 'rgba(232, 234, 240, 0.85)';
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(step);
    };

    const onMouseMove = e => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.active = true;
    };
    const onMouseLeave = () => { mouse.active = false; mouse.x = -9999; mouse.y = -9999; };

    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        cancelAnimationFrame(rafRef.current);
      } else {
        rafRef.current = requestAnimationFrame(step);
      }
    };

    resize();
    seed();
    rafRef.current = requestAnimationFrame(step);

    const ro = new ResizeObserver(() => { resize(); seed(); });
    ro.observe(canvas);

    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseleave', onMouseLeave);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseleave', onMouseLeave);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return (
    <div className="auth-hero">
      <canvas ref={canvasRef} className="auth-hero-canvas"/>
      <div className="auth-hero-overlay">
        <div className="auth-hero-mark">
          <span className="auth-hero-mark-glyph">M</span>
        </div>
        <h1 className="auth-hero-title">Maestro</h1>
        <p className="auth-hero-tagline">Conduct your knowledge.</p>
        <div className="auth-hero-meta">
          <span>Multi-Agent RAG</span>
          <span className="auth-hero-dot">·</span>
          <span>RAPTOR Retrieval</span>
          <span className="auth-hero-dot">·</span>
          <span>LangGraph</span>
        </div>
      </div>
    </div>
  );
}
