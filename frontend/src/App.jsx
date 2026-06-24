import React from 'react';
import Dashboard from './pages/Dashboard';

function App() {
  return (
    <div className="min-h-screen w-screen overflow-y-auto bg-[var(--app-bg)] text-[var(--app-text)] font-sans selection:bg-[var(--brand-100)]">
      <Dashboard />
    </div>
  );
}

export default App;
