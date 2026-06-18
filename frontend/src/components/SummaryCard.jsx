import React from 'react';

const SummaryCard = ({ quality }) => {
  const metrics = [
    { label: 'Quality', value: `${quality || 0}%` },
    { label: 'Reduction', value: '94%' },
    { label: 'Speech', value: '98%' },
    { label: 'Stability', value: '99%' },
  ];

  return (
    <div className="p-6 border border-zinc-800/50 rounded-2xl bg-zinc-900/20 col-span-1 lg:col-span-2">
      <h3 className="text-sm font-normal text-zinc-300 mb-8">Summary</h3>
      <div className="grid grid-cols-2 gap-y-8 gap-x-4">
        {metrics.map((m, idx) => (
          <div key={idx}>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">{m.label}</div>
            <div className="text-xl font-light text-zinc-200">{m.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SummaryCard;
