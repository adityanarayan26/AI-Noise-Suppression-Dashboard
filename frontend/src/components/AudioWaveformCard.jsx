import React from 'react';

// Static fallback bars shown before WebSocket connects
const MOCK_BARS = Array.from({ length: 50 }).map((_, i) => {
  const height = 8 + Math.sin(i * 0.4) * 6 + Math.sin(i * 0.15) * 8;
  return Math.max(4, height);
});

/**
 * AudioWaveformCard
 *
 * Props:
 *   bars              {number[]} — 50 bar heights (0–100) from live WebSocket metrics.
 *   suppressionEnabled {boolean} — changes bar colour when AI suppression is active.
 *   isConnected       {boolean} — drives the Live / Standby label & dot animation.
 */
const AudioWaveformCard = ({ bars, suppressionEnabled, isConnected }) => {
  // Always use 50 real bars when connected; fall back to the static mockup otherwise.
  const hasLiveBars = bars && bars.some(b => b > 0);
  const displayBars = hasLiveBars ? bars : MOCK_BARS;

  // Bar colour: green when suppression on, indigo when live (suppression off), gray in standby
  const barColour = !isConnected
    ? 'bg-zinc-300'
    : suppressionEnabled
      ? 'bg-emerald-500'
      : 'bg-indigo-500';

  // Subtle opacity for standby bars so the animation is clearly "off"
  const barOpacity = isConnected ? 'opacity-90' : 'opacity-30';

  return (
    <div className="h-full p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col">
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-5 shrink-0">
        <h3 className="text-sm font-medium text-zinc-900">Live Activity</h3>
        <div className="flex items-center gap-3">
          {/* Suppression badge */}
          {suppressionEnabled !== undefined && (
            <span
              className={`text-[10px] tracking-widest uppercase font-semibold px-2 py-0.5 rounded transition-all duration-300 ${suppressionEnabled
                  ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300'
                  : 'bg-zinc-200 text-zinc-500'
                }`}
            >
              {suppressionEnabled ? 'AI Suppression On' : 'Suppression Off'}
            </span>
          )}

          {/* Live / Standby indicator — driven by isConnected, not bar values */}
          <span
            className={`text-[10px] tracking-widest uppercase flex items-center gap-1.5 font-medium transition-colors duration-300 ${isConnected ? 'text-zinc-700' : 'text-zinc-400'
              }`}
          >
            {isConnected && (
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse inline-block" />
            )}
            {isConnected ? 'Live' : 'Standby'}
          </span>
        </div>

      </div>

      {/* ── Waveform bars ── */}
      <div className="flex-1 flex items-end justify-between gap-[2px] min-h-0">
        {displayBars.map((height, i) => (
          <div
            key={i}
            className={`w-full rounded-t-sm ${barColour} ${barOpacity} transition-all duration-100`}
            style={{ height: `${Math.max(2, Math.min(100, height))}%` }}
          />
        ))}
      </div>
    </div>
  );
};

export default AudioWaveformCard;
