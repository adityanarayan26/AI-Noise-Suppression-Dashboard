import React from 'react';

// Static mockup data to prevent re-rendering visual glitch when no live data
const MOCK_BARS = Array.from({ length: 50 }).map((_, i) => {
  const height = 10 + Math.random() * 40 + Math.sin(i * 0.5) * 30;
  return Math.max(5, height);
});

/**
 * AudioWaveformCard
 *
 * Displays a bar-chart waveform visualisation.
 *
 * Props:
 *   bars {number[]} — optional array of 50 bar heights (0–100).
 *                     When provided (live mode), displays real-time audio data.
 *                     Falls back to MOCK_BARS when not connected.
 *   suppressionEnabled {boolean} — shows suppression status badge
 */
const AudioWaveformCard = ({ bars, suppressionEnabled }) => {
  const displayBars = (bars && bars.length > 0) ? bars : MOCK_BARS;
  const isLive = bars && bars.length > 0;

  return (
    <div className="h-full p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col">
      <div className="flex items-center justify-between mb-6 shrink-0">
        <h3 className="text-sm font-medium text-zinc-900">Live Activity</h3>
        <div className="flex items-center gap-3">
          {suppressionEnabled !== undefined && (
            <span className={`text-[10px] tracking-widest uppercase font-medium px-2 py-0.5 rounded ${suppressionEnabled ? 'bg-zinc-900 text-white' : 'bg-zinc-200 text-zinc-600'}`}>
              {suppressionEnabled ? 'Suppression On' : 'Suppression Off'}
            </span>
          )}
          <span className={`text-[10px] tracking-widest uppercase flex items-center gap-1.5 ${isLive ? 'text-zinc-700' : 'text-zinc-400'}`}>
            {isLive && <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse inline-block" />}
            {isLive ? 'Recording' : 'Standby'}
          </span>
        </div>
      </div>

      <div className="flex-1 flex items-end justify-between space-x-[2px]">
        {displayBars.map((height, i) => (
          <div
            key={i}
            className={`w-full rounded-t-sm opacity-80 transition-all duration-75 ${isLive ? 'bg-zinc-700' : 'bg-zinc-400'}`}
            style={{ height: `${Math.max(2, height)}%` }}
          />
        ))}
      </div>
    </div>
  );
};

export default AudioWaveformCard;
