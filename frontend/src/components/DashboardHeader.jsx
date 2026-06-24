import React from 'react';

const DashboardHeader = ({ systemStatus }) => {
  return (
    <div className="flex items-center justify-between pb-6 mb-6 border-b border-[var(--panel-border)] shrink-0">
      <h1 className="text-xl font-medium tracking-tight text-[var(--app-text)]">AI Noise Suppression Dashboard</h1>
      <div className="flex items-center space-x-3">
        <span className="text-xs uppercase tracking-widest text-[var(--brand-700)]">{systemStatus || 'Offline'}</span>
        <span className={`w-2 h-2 rounded-full ${systemStatus === 'online' ? 'bg-[var(--brand-500)]' : 'bg-red-500'}`} />
      </div>
    </div>
  );
};

export default DashboardHeader;
