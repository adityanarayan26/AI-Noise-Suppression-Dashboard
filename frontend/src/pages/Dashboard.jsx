import React, { useState, useEffect } from 'react';
import DashboardHeader from '../components/DashboardHeader';
import MicrophoneStatusCard from '../components/MicrophoneStatusCard';
import NoiseLevelCard from '../components/NoiseLevelCard';
import VoiceQualityCard from '../components/VoiceQualityCard';
import LatencyCard from '../components/LatencyCard';
import AudioWaveformCard from '../components/AudioWaveformCard';
import AlertPanel from '../components/AlertPanel';
import { healthService, metricsService, audioService } from '../services/api';

const Dashboard = () => {
  const [systemStatus, setSystemStatus] = useState('loading');
  const [metrics, setMetrics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [healthRes, metricsRes, alertsRes] = await Promise.all([
          healthService.getHealth().catch(() => ({ data: { status: 'offline' } })),
          metricsService.getMetrics(),
          audioService.getAlerts()
        ]);
        setSystemStatus(healthRes.data.status);
        setMetrics(metricsRes.data);
        setAlerts(alertsRes.data);
      } catch (err) {
        setSystemStatus('offline');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !metrics) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500 text-sm tracking-widest uppercase">
        Loading...
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col max-w-6xl mx-auto px-6 py-8">
      <DashboardHeader systemStatus={systemStatus} />

      <div className="flex-1 min-h-0 flex flex-col gap-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 shrink-0">
          <MicrophoneStatusCard status={metrics?.microphone_status} />
          <NoiseLevelCard score={metrics?.noise_score} />
          <VoiceQualityCard clarity={metrics?.voice_clarity} />
          <LatencyCard latency={metrics?.latency} />
        </div>

        {/* Main View: Waveform & Alerts */}
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 h-full">
            <AudioWaveformCard />
          </div>
          <div className="md:col-span-1 h-full">
            <AlertPanel alerts={alerts} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
