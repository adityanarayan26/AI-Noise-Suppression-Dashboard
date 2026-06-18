import React from 'react';

const MicrophoneStatusCard = ({ status }) => {
  return (
    <div className="p-5 border border-zinc-300 rounded-xl bg-zinc-100/50">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2">Microphone</div>
      <div className="text-lg font-medium text-zinc-900 capitalize">{status || 'Unknown'}</div>
    </div>
  );
};

export default MicrophoneStatusCard;
