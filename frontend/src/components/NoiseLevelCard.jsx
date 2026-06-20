import React from 'react';

const NoiseLevelCard = ({ score }) => {
  const value = Math.min(100, Math.max(0, score || 0));

  // Colour changes dynamically with the score
  const barColour =
    value <= 30 ? 'bg-green-500' :
    value <= 60 ? 'bg-amber-400' :
    'bg-red-500';

  const textColour =
    value <= 30 ? 'text-green-600' :
    value <= 60 ? 'text-amber-600' :
    'text-red-500';

  return (
    <div className="p-5 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col gap-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Noise Level</div>

      <div className="flex items-baseline gap-1">
        <span className={`text-xl font-bold tabular-nums transition-colors duration-300 ${textColour}`}>
          {value}
        </span>
        <span className="text-xs text-zinc-400">/ 100</span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-zinc-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColour}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
};

export default NoiseLevelCard;
