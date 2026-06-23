import React from 'react';

const STATUS_CONFIG = {
    connected: {
        dot: 'bg-green-500 animate-pulse',
        text: 'text-green-600',
        label: 'Connected',
    },
    silent: {
        dot: 'bg-amber-400',
        text: 'text-amber-600',
        label: 'Silent',
    },
    disconnected: {
        dot: 'bg-red-500',
        text: 'text-red-500',
        label: 'Disconnected',
    },
};

const MicrophoneStatusCard = ({ status }) => {
    const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.disconnected;

    return (
        <div className="p-5 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col gap-2">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Microphone</div>
            <div className="flex items-center gap-2 mt-1">
                <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${cfg.dot}`} />
                <span className={`text-base font-semibold capitalize ${cfg.text} transition-colors duration-300`}>
                    {cfg.label}
                </span>
            </div>
        </div>
    );
};

export default MicrophoneStatusCard;
