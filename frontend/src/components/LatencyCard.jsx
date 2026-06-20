import React from 'react';

const LatencyCard = ({ latency }) => {
  const value = latency || 0;

  // Good <50 ms, acceptable 50–150 ms, bad >150 ms
  const textColour =
    value < 50 ? 'text-green-600' :
      value < 150 ? 'text-amber-600' :
        'text-red-500';

  const label =
    value < 50 ? 'Good' :
      value < 150 ? 'Fair' :
        'High';

  const dotColour =
    value < 50 ? 'bg-green-500' :
      value < 150 ? 'bg-amber-400' :
        'bg-red-500';

  return (
    <div className="p-5 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col gap-2">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Latency</div>

      <div className="flex items-baseline gap-1 mt-1">
        <span className={`text-xl font-bold tabular-nums transition-colors duration-300 ${textColour}`}>
          {value}
        </span>
        <span className="text-xs text-zinc-400">ms</span>
      </div>

      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 transition-colors duration-300 ${dotColour}`} />
        <span className={`text-[10px] font-medium uppercase tracking-wider transition-colors duration-300 ${textColour}`}>
          {label}
        </span>
      </div>
    </div>
  );
};

export default LatencyCard;
