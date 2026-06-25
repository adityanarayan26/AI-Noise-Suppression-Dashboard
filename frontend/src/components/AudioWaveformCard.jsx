import React, { useRef, useEffect, useCallback } from 'react';

// Static sine-wave fallback shown in standby
const MOCK_BARS = Array.from({ length: 50 }).map((_, i) => {
  const h = 8 + Math.sin(i * 0.4) * 6 + Math.sin(i * 0.15) * 8;
  return Math.max(4, h);
});

/**
 * AudioWaveformCard
 *
 * Props:
 *   bars              {number[]} — 50 bar heights (0-100), fallback when no live analyser
 *   suppressionEnabled {boolean}
 *   isConnected       {boolean}
 *   isLive            {boolean}  — true during live listening AND during 5s recording
 *   isRecording       {boolean}  — true during 5s recording phase
 *   getAnalyserNode   {() => AnalyserNode | null} — returns the live Web Audio analyser
 *   sourceLabel       {string}
 */
const AudioWaveformCard = ({
  bars,
  suppressionEnabled,
  isConnected,
  isLive = false,
  isRecording = false,
  getAnalyserNode,
  sourceLabel = 'Live Microphone',
}) => {
  const canvasRef = useRef(null);
  const rafRef = useRef(null);
  const dataRef = useRef(null);
  const smoothBarsRef = useRef(new Float32Array(50).fill(0.03));

  // ── Drawing loop ──────────────────────────────────────────────────────
  const startCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const draw = () => {
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
      const W = canvas.width / dpr;
      const H = canvas.height / dpr;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      const analyser = getAnalyserNode ? getAnalyserNode() : null;
      const barColor = !isConnected
        ? '#b4dcc3'
        : isRecording
          ? '#ef4444'
          : suppressionEnabled
            ? '#008740'
            : '#00b359';

      if (analyser) {
        // ── Live path: draw directly from AnalyserNode ─────────────────
        if (!dataRef.current || dataRef.current.length !== analyser.fftSize) {
          dataRef.current = new Float32Array(analyser.fftSize);
        }
        analyser.getFloatTimeDomainData(dataRef.current);

        const BAR_COUNT = 50;
        const step = Math.floor(dataRef.current.length / BAR_COUNT);

        // Dynamic normalisation: find frame peak
        let framePeak = 0;
        for (let i = 0; i < dataRef.current.length; i++) {
          const a = Math.abs(dataRef.current[i]);
          if (a > framePeak) framePeak = a;
        }
        const normalizer = Math.max(framePeak, 0.005);

        const barW = W / BAR_COUNT;
        const gap = Math.max(1, barW * 0.18);
        const bW = barW - gap;

        for (let i = 0; i < BAR_COUNT; i++) {
          const start = i * step;
          const end = Math.min(dataRef.current.length, start + step);
          let sum = 0;

          for (let j = start; j < end; j++) {
            const s = dataRef.current[j];
            sum += s * s;
          }

          const rms = Math.sqrt(sum / (end - start));

          // Ignore tiny background noise
          const noiseFloor = 0.005;

          const adjusted = Math.max(0, rms - noiseFloor);

          // Fixed gain
          const target = Math.min(adjusted * 8, 1);
          const prev = smoothBarsRef.current[i];
          smoothBarsRef.current[i] = prev + (target - prev) * (target > prev ? 0.25 : 0.88);

          const barH = Math.max(2, smoothBarsRef.current[i] * H);
          const x = i * barW + gap / 2;
          const y = H - barH;
          const radius = Math.min(bW / 2, 3);

          ctx.fillStyle = barColor;
          ctx.globalAlpha = 0.9;
          ctx.beginPath();
          if (barH > radius * 2) {
            ctx.moveTo(x + radius, y);
            ctx.lineTo(x + bW - radius, y);
            ctx.quadraticCurveTo(x + bW, y, x + bW, y + radius);
            ctx.lineTo(x + bW, H);
            ctx.lineTo(x, H);
            ctx.lineTo(x, y + radius);
            ctx.quadraticCurveTo(x, y, x + radius, y);
          } else {
            ctx.rect(x, y, bW, barH);
          }
          ctx.closePath();
          ctx.fill();
          ctx.globalAlpha = 1;
        }
      } else {
        // ── Fallback: draw from bars prop or MOCK_BARS ──────────────────
        const displayBars = Array.isArray(bars) && bars.length > 0 ? bars : MOCK_BARS;
        const BAR_COUNT = displayBars.length;
        const barW = W / BAR_COUNT;
        const gap = Math.max(1, barW * 0.18);
        const bW = barW - gap;
        const alpha = isConnected ? 0.85 : 0.3;

        for (let i = 0; i < BAR_COUNT; i++) {
          const pct = Math.max(2, Math.min(100, displayBars[i])) / 100;
          const barH = Math.max(2, pct * H);
          const x = i * barW + gap / 2;
          const y = H - barH;
          const radius = Math.min(bW / 2, 3);

          ctx.fillStyle = barColor;
          ctx.globalAlpha = alpha;
          ctx.beginPath();
          if (barH > radius * 2) {
            ctx.moveTo(x + radius, y);
            ctx.lineTo(x + bW - radius, y);
            ctx.quadraticCurveTo(x + bW, y, x + bW, y + radius);
            ctx.lineTo(x + bW, H);
            ctx.lineTo(x, H);
            ctx.lineTo(x, y + radius);
            ctx.quadraticCurveTo(x, y, x + radius, y);
          } else {
            ctx.rect(x, y, bW, barH);
          }
          ctx.closePath();
          ctx.fill();
          ctx.globalAlpha = 1;
        }
      }

      ctx.restore();
      rafRef.current = requestAnimationFrame(draw);
    };

    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    draw();
  }, [bars, suppressionEnabled, isConnected, isLive, isRecording, getAnalyserNode]);

  const stopCanvas = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  // Resize canvas to match CSS display size at device pixel ratio
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        canvas.width = Math.round(rect.width * dpr);
        canvas.height = Math.round(rect.height * dpr);
      }
    };

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    return () => ro.disconnect();
  }, []);

  // Start/restart drawing loop whenever props change
  useEffect(() => {
    startCanvas();
    return stopCanvas;
  }, [startCanvas, stopCanvas]);

  // ── Status label ──────────────────────────────────────────────────────
  const liveLabel = isRecording
    ? 'Recording'
    : isLive
      ? 'Live'
      : isConnected
        ? 'Connected'
        : 'Standby';

  const dotColor = isRecording
    ? 'bg-red-500'
    : isLive
      ? 'bg-[var(--brand-500)]'
      : 'bg-[var(--brand-300)]';

  const labelColor = isRecording
    ? 'text-red-500'
    : isLive || isConnected
      ? 'text-[var(--brand-700)]'
      : 'text-[var(--brand-300)]';

  const shouldPulse = isLive || isRecording;

  return (
    <div className="h-full p-6 border border-[var(--panel-border)] rounded-xl bg-[var(--panel-bg)] backdrop-blur-sm flex flex-col shadow-[0_14px_40px_rgba(0,135,64,0.08)]">
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-5 shrink-0">
        <div>
          <h3 className="text-sm font-medium text-[var(--app-text)]">Audio Activity</h3>
          <p className="text-[10px] text-[var(--brand-700)] uppercase tracking-widest mt-0.5">{sourceLabel}</p>
        </div>
        <div className="flex items-center gap-3">
          {suppressionEnabled !== undefined && (
            <span
              className={`text-[10px] tracking-widest uppercase font-semibold px-2 py-0.5 rounded transition-all duration-300 ${suppressionEnabled
                ? 'bg-[var(--brand-100)] text-[var(--brand-700)] ring-1 ring-[var(--brand-300)]'
                : 'bg-[var(--brand-50)] text-[var(--brand-700)] ring-1 ring-[var(--brand-200)]'
                }`}
            >
              {suppressionEnabled ? 'AI Suppression On' : 'Suppression Off'}
            </span>
          )}

          <span
            className={`text-[10px] tracking-widest uppercase flex items-center gap-1.5 font-medium transition-colors duration-300 ${labelColor}`}
          >
            {(isLive || isRecording) && (
              <span className={`w-1.5 h-1.5 rounded-full ${dotColor} ${shouldPulse ? 'animate-pulse' : ''} inline-block`} />
            )}
            {liveLabel}
          </span>
        </div>
      </div>

      {/* ── Canvas Waveform ── */}
      <div className="flex-1 min-h-0 relative">
        <canvas ref={canvasRef} className="w-full h-full block" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-[var(--brand-100)] opacity-50" />
      </div>
    </div>
  );
};

export default AudioWaveformCard;