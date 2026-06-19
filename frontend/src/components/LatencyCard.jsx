import React from 'react';

const LatencyCard = ({ latency }) => {
  return (
    <div className="rounded-[24px] lg:rounded-[32px] border border-slate-200 shadow-sm hover:shadow-md bg-[#f8fafc] p-5 lg:p-6 h-full flex flex-col justify-between">
      <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Latency</div>
      <div className="flex items-baseline space-x-1">
        <span className="text-2xl font-black tracking-tight text-slate-900">{latency || 0}</span>
        <span className="text-sm font-medium text-slate-500">ms</span>
      </div>
    </div>
  );
};

export default LatencyCard;
