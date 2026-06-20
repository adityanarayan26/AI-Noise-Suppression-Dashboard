import React from 'react';

const LEVEL_CONFIG = {
  critical: {
    border: 'border-l-red-500',
    bg: 'bg-red-50',
    badge: 'bg-red-100 text-red-600',
    dot: 'bg-red-500',
    textColour: 'text-red-700',
  },
  warning: {
    border: 'border-l-amber-400',
    bg: 'bg-amber-50',
    badge: 'bg-amber-100 text-amber-600',
    dot: 'bg-amber-400',
    textColour: 'text-amber-700',
  },
  info: {
    border: 'border-l-blue-400',
    bg: 'bg-blue-50',
    badge: 'bg-blue-100 text-blue-600',
    dot: 'bg-blue-400',
    textColour: 'text-blue-700',
  },
};

const AlertPanel = ({ alerts = [] }) => {
  return (
    <div className="h-full p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col min-h-[200px]">
      <div className="flex items-center justify-between mb-4 shrink-0">
        <h3 className="text-sm font-medium text-zinc-900">Recent Alerts</h3>
        {alerts.length > 0 && (
          <span className="text-[10px] font-semibold bg-zinc-200 text-zinc-600 px-2 py-0.5 rounded-full uppercase tracking-wider">
            {alerts.length}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {alerts.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-zinc-400 mt-2">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            All clear — no active alerts
          </div>
        ) : (
          alerts.map((alert, idx) => {
            const cfg = LEVEL_CONFIG[alert.level] || LEVEL_CONFIG.info;
            return (
              <div
                key={idx}
                className={`flex gap-3 items-start p-3 rounded-lg border-l-4 ${cfg.border} ${cfg.bg} transition-all duration-200`}
              >
                <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                <div className="min-w-0">
                  <p className={`text-xs font-medium leading-snug ${cfg.textColour}`}>
                    {alert.message}
                  </p>
                  <span className="text-[10px] text-zinc-400 uppercase tracking-widest mt-0.5 block">
                    {alert.time}
                  </span>
                </div>
                {alert.level && (
                  <span className={`ml-auto text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded flex-shrink-0 ${cfg.badge}`}>
                    {alert.level}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default AlertPanel;
