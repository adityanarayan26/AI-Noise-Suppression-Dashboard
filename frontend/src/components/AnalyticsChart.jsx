import React from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

const mockData = [
  { time: '10:00', value: 20 },
  { time: '10:05', value: 22 },
  { time: '10:10', value: 45 },
  { time: '10:15', value: 25 },
  { time: '10:20', value: 24 },
  { time: '10:25', value: 28 },
  { time: '10:30', value: 24 },
];

const AnalyticsChart = () => {
  return (
    <div className="p-6 border border-zinc-800/50 rounded-2xl bg-zinc-900/20 col-span-1 md:col-span-2 lg:col-span-3">
      <h3 className="text-sm font-normal text-zinc-300 mb-8">Trends</h3>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="h-32">
          <h4 className="text-[10px] text-zinc-500 uppercase tracking-widest mb-4">Noise</h4>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={mockData}>
              <Line type="monotone" dataKey="value" stroke="#71717a" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="h-32">
          <h4 className="text-[10px] text-zinc-500 uppercase tracking-widest mb-4">Voice Quality</h4>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={mockData}>
              <Line type="monotone" dataKey="value" stroke="#a1a1aa" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="h-32">
          <h4 className="text-[10px] text-zinc-500 uppercase tracking-widest mb-4">Latency</h4>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={mockData}>
              <Line type="monotone" dataKey="value" stroke="#52525b" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default AnalyticsChart;
