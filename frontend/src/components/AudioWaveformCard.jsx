import React from 'react';

// Static mockup data to prevent re-rendering visual glitch
const MOCK_BARS = Array.from({ length: 50 }).map((_, i) => {
  const height = 10 + Math.random() * 40 + Math.sin(i * 0.5) * 30;
  return Math.max(5, height);
});

const AudioWaveformCard = () => {
  /*
   * INTERN ASSIGNMENT:
   * To connect this visualization with a live backend:
   * 1. Set up a WebSocket or WebRTC connection in your frontend services.
   * 2. Replace the `MOCK_BARS` with a React state variable (e.g., `const [bars, setBars] = useState([])`).
   * 3. Update the state dynamically as you receive audio volume/frequency packets from your backend.
   * 4. Make sure to close the connection properly in a `useEffect` cleanup function.
   */

  return (
    <div className="h-full p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col">
      <div className="flex items-center justify-between mb-6 shrink-0">
        <h3 className="text-sm font-medium text-zinc-900">Live Activity</h3>
        <span className="text-[10px] tracking-widest text-zinc-500 uppercase">Recording</span>
      </div>
      
      <div className="flex-1 flex items-end justify-between space-x-[2px]">
        {MOCK_BARS.map((height, i) => (
          <div 
            key={i} 
            className="w-full bg-zinc-400 rounded-t-sm opacity-80"
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
    </div>
  );
};

export default AudioWaveformCard;
