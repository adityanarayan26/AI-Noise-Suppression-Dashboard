import React from 'react';

const VoiceQualityCard = ({ clarity }) => {
  return (
    <div className="p-5 border border-zinc-300 rounded-xl bg-zinc-100/50">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2">Voice Clarity</div>
      <div className="flex items-baseline space-x-1">
        <span className="text-lg font-medium text-zinc-900">{clarity || 0}</span>
        <span className="text-xs text-zinc-500">/ 100</span>
      </div>
    </div>
  );
};

export default VoiceQualityCard;
