import React, { useState, useEffect } from 'react';
import DashboardHeader from '../components/DashboardHeader';
import MicrophoneStatusCard from '../components/MicrophoneStatusCard';
import NoiseLevelCard from '../components/NoiseLevelCard';
import VoiceQualityCard from '../components/VoiceQualityCard';
import LatencyCard from '../components/LatencyCard';
import AudioWaveformCard from '../components/AudioWaveformCard';
import AlertPanel from '../components/AlertPanel';
import NoiseSuppessionPanel from '../components/NoiseSuppessionPanel';
import { useAudioWebSocket } from '../hooks/useAudioWebSocket';
import { healthService } from '../services/api';

const Dashboard = () => {
  // System health (HTTP poll — backend online/offline check)
  const [systemStatus, setSystemStatus] = useState('loading');

  // ── Real-time audio WebSocket hook ──────────────────────────────────────
  const {
    isConnected,
    metrics,
    suppressionEnabled,
    toggleSuppression,
    isRecording,
    isProcessing,
    beforeUrl,
    afterUrl,
    snrBefore,
    snrAfter,
    recordAndProcess,
    resetComparison,
    error: wsError,
  } = useAudioWebSocket();

  // ── Health check (HTTP) ─────────────────────────────────────────────────
  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await healthService.getHealth().catch(() => ({ data: { status: 'offline' } }));
        setSystemStatus(res.data.status);
      } catch {
        setSystemStatus('offline');
      }
    };
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // Show loading only on very first render before any metric arrives
  const loading = metrics.noise_score === 0 && metrics.voice_clarity === 0 && !isConnected;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500 text-sm tracking-widest uppercase">
        Loading...
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col max-w-6xl mx-auto px-6 py-8 overflow-y-auto">
      <DashboardHeader systemStatus={isConnected ? 'online' : systemStatus} />

      {/* WebSocket error banner */}
      {wsError && (
        <div className="mb-4 px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600 shrink-0">
          ⚠ {wsError}
        </div>
      )}

      <div className="flex flex-col gap-6">
        {/* KPI Cards — fed with live WebSocket metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 shrink-0">
          <MicrophoneStatusCard status={metrics.microphone_status} />
          <NoiseLevelCard score={metrics.noise_score} />
          <VoiceQualityCard clarity={metrics.voice_clarity} />
          <LatencyCard latency={metrics.latency} />
        </div>

        {/* Main View: Waveform & Alerts */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6" style={{ minHeight: '220px' }}>
          <div className="md:col-span-2 h-full">
            <AudioWaveformCard
              bars={metrics.waveform_bars}
              suppressionEnabled={suppressionEnabled}
            />
          </div>
          <div className="md:col-span-1 h-full">
            {/* Use live alerts when connected, otherwise show static fallback */}
            <AlertPanel alerts={metrics.alerts && metrics.alerts.length > 0 ? metrics.alerts : []} />
          </div>
        </div>

        {/* AI Noise Suppression Comparison — new real-time section */}
        <NoiseSuppessionPanel
          suppressionEnabled={suppressionEnabled}
          toggleSuppression={toggleSuppression}
          isRecording={isRecording}
          isProcessing={isProcessing}
          beforeUrl={beforeUrl}
          afterUrl={afterUrl}
          snrBefore={snrBefore}
          snrAfter={snrAfter}
          recordAndProcess={recordAndProcess}
          resetComparison={resetComparison}
          noiseClass={metrics.noise_class}
          noiseConfidence={metrics.noise_confidence}
          snrDb={metrics.snr_db}
          speechPresence={metrics.speech_presence}
          isConnected={isConnected}
        />
      </div>
    </div>
  );
};

export default Dashboard;
