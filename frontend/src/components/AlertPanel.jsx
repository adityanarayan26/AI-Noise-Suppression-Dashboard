import React from 'react';

const AlertPanel = ({ alerts = [] }) => {
  return (
    <div className="h-full p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col min-h-[200px]">
      <h3 className="text-sm font-medium text-zinc-900 mb-4 shrink-0">Recent Alerts</h3>
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {alerts.length === 0 ? (
          <div className="text-xs text-zinc-500">No active alerts</div>
        ) : (
          alerts.map((alert, idx) => (
            <div key={idx} className="pb-3 border-b border-zinc-200 last:border-0">
              <p className="text-sm text-zinc-700">{alert.message}</p>
              <span className="text-[10px] text-zinc-400 uppercase tracking-widest mt-1 block">{alert.time}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default AlertPanel;
