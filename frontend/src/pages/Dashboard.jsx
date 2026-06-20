import React, { useState, useEffect } from 'react';
import DashboardHeader from '../components/DashboardHeader';
import MicrophoneStatusCard from '../components/MicrophoneStatusCard';
import NoiseLevelCard from '../components/NoiseLevelCard';
import VoiceQualityCard from '../components/VoiceQualityCard';
import LatencyCard from '../components/LatencyCard';
import AudioUploadCard from '../components/AudioUploadCard';
import AudioWaveformCard from '../components/AudioWaveformCard';
import LiveMicrophoneCard from '../components/LiveMicrophoneCard';
import AlertPanel from '../components/AlertPanel';
import CloudinaryGallery from '../components/CloudinaryGallery';
import { healthService, metricsService, audioService } from '../services/api';

const Dashboard = () => {
  const [systemStatus, setSystemStatus] = useState('loading');
  const [metrics, setMetrics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadCount, setUploadCount] = useState(0);

  const fetchData = async () => {
    try {
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

  useEffect(() => {
    fetchData();
    // Poll for alerts and online status check every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleUploadSuccess = (data) => {
    // Instantly update UI metrics from the processed audio file results
    setMetrics({
      microphone_status: 'connected',
      noise_score: data.noise_score,
      voice_clarity: data.voice_clarity,
      latency: metrics?.latency || 50,
      audio_quality: data.audio_quality
    });
    // Refresh alerts to show the new classification log
    audioService.getAlerts().then((res) => {
      setAlerts(res.data);
    });
    // Trigger Cloudinary gallery refresh
    setUploadCount(prev => prev + 1);
  };

  if (loading && !metrics) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-950 text-slate-400 gap-4">
        <div className="h-7 w-7 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
        <div className="text-[10px] tracking-widest uppercase font-semibold text-slate-500">
          Loading Dashboard...
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto flex flex-col max-w-6xl mx-auto px-6 py-8">
      <DashboardHeader systemStatus={systemStatus} />

      <div className="flex flex-col gap-6 pb-12">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 shrink-0">
          <MicrophoneStatusCard status={metrics?.microphone_status} />
          <NoiseLevelCard score={metrics?.noise_score} />
          <VoiceQualityCard clarity={metrics?.voice_clarity} />
          <LatencyCard latency={metrics?.latency} />
        </div>

        {/* Main View: Left side has stack of Upload and Visualizer, Right side has Alerts */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 shrink-0">
          <div className="md:col-span-2 flex flex-col gap-6">
            <div className="flex-1 min-h-fit">
              <AudioUploadCard onUploadSuccess={handleUploadSuccess} />
            </div>
            <div className="min-h-fit">
              <AudioWaveformCard onUploadSuccess={handleUploadSuccess} />
            </div>
          </div>
          <div className="md:col-span-1 flex flex-col gap-6">
            <div className="min-h-fit">
              <LiveMicrophoneCard />
            </div>
            <div className="flex-1 min-h-[300px]">
              <AlertPanel alerts={alerts} />
            </div>
          </div>
        </div>

        {/* Cloudinary Gallery */}
        <CloudinaryGallery refreshTrigger={uploadCount} />
      </div>
    </div>
  );
};

export default Dashboard;
