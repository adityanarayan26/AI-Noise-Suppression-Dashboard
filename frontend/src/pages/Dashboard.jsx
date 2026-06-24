import React, { useState, useEffect } from 'react';
import DashboardHeader from '../components/DashboardHeader';
import MicrophoneStatusCard from '../components/MicrophoneStatusCard';
import NoiseLevelCard from '../components/NoiseLevelCard';
import VoiceQualityCard from '../components/VoiceQualityCard';
import LatencyCard from '../components/LatencyCard';
import AudioUploadCard from '../components/AudioUploadCard';
import AudioWaveformCard from '../components/AudioWaveformCard';
import AlertPanel from '../components/AlertPanel';
import CloudinaryGallery from '../components/CloudinaryGallery';
import NoiseSuppessionPanel from '../components/NoiseSuppessionPanel';
import { healthService, metricsService, audioService, mediaUrl } from '../services/api';
import { useAudioWebSocket } from '../hooks/useAudioWebSocket';

const Dashboard = () => {
  const [systemStatus, setSystemStatus] = useState('loading');
  const [restMetrics, setRestMetrics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadCount, setUploadCount] = useState(0);
  const [uploadedMetrics, setUploadedMetrics] = useState(null);
  const [uploadedComparison, setUploadedComparison] = useState(null);

  // --- Live WebSocket connection ---
  const {
    isConnected,
    isCapturing,
    error: wsError,
    metrics: liveMetrics,
    liveWaveformBars,
    suppressionEnabled,
    toggleSuppression,
    startCapture,
    stopCapture,
    playbackEnabled,
    togglePlayback,
    isRecording,
    isProcessing,
    beforeUrl,
    afterUrl,
    snrBefore,
    snrAfter,
    recordAndProcess,
    resetComparison,
  } = useAudioWebSocket();

  // Merge live metrics with REST-fetched fallback
  const liveDisplayMetrics = isConnected
    ? {
      microphone_status: liveMetrics.microphone_status || 'connected',
      noise_score: liveMetrics.noise_score ?? restMetrics?.noise_score ?? 0,
      voice_clarity: liveMetrics.voice_clarity ?? restMetrics?.voice_clarity ?? 0,
      latency: liveMetrics.latency ?? restMetrics?.latency ?? 0,
      audio_quality: liveMetrics.audio_quality ?? restMetrics?.audio_quality ?? 0,
      noise_class: liveMetrics.noise_class ?? restMetrics?.noise_class ?? 'Other',
      noise_confidence: liveMetrics.noise_confidence ?? restMetrics?.noise_confidence ?? 0,
      snr_db: liveMetrics.snr_db ?? restMetrics?.snr_db ?? 0,
      speech_presence: liveMetrics.speech_presence ?? restMetrics?.speech_presence ?? false,
      engine: liveMetrics.engine ?? restMetrics?.engine,
      deepfilternet_active: liveMetrics.deepfilternet_active ?? restMetrics?.deepfilternet_active,
    }
    : { ...restMetrics };

  const displayMetrics = uploadedMetrics || liveDisplayMetrics;

  const fetchData = async () => {
    try {
      const [healthRes, metricsRes, alertsRes] = await Promise.all([
        healthService.getHealth().catch(() => ({ data: { status: 'offline' } })),
        metricsService.getMetrics(),
        audioService.getAlerts()
      ]);
      setSystemStatus(healthRes.data.status);
      setRestMetrics(prev => ({ ...prev, ...metricsRes.data }));
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
    const nextMetrics = {
      microphone_status: 'connected',
      noise_score: data.noise_score,
      voice_clarity: data.voice_clarity,
      latency: data.latency ?? restMetrics?.latency ?? 50,
      audio_quality: data.audio_quality,
      noise_class: data.noise_type,
      noise_confidence: data.noise_confidence ?? 0,
      snr_db: data.snr_db,
      speech_presence: Boolean(data.speech_presence),
      waveform_bars: data.waveform_bars,
      engine: data.engine,
      deepfilternet_active: data.deepfilternet_active,
    };
    setUploadedMetrics(nextMetrics);
    setUploadedComparison({
      beforeUrl: mediaUrl(data.original_audio_url),
      afterUrl: mediaUrl(data.clean_audio_url),
      snrBefore: data.snr_before_db,
      snrAfter: data.snr_after_db,
    });
    setRestMetrics(prev => ({ ...prev, ...nextMetrics }));
    // Refresh alerts to show the new classification log
    audioService.getAlerts().then((res) => {
      setAlerts(res.data);
    });
    // Trigger Cloudinary gallery refresh
    setUploadCount(prev => prev + 1);
  };

  const clearUploadedMetrics = () => {
    setUploadedMetrics(null);
    setUploadedComparison(null);
  };

  const comparisonBeforeUrl = uploadedComparison?.beforeUrl || beforeUrl;
  const comparisonAfterUrl = uploadedComparison?.afterUrl || afterUrl;
  const comparisonSnrBefore = uploadedComparison?.snrBefore ?? snrBefore;
  const comparisonSnrAfter = uploadedComparison?.snrAfter ?? snrAfter;
  const micIsLive = isConnected && isCapturing;
  const activeBars = uploadedMetrics?.waveform_bars
    || (micIsLive ? liveWaveformBars : null)
    || liveMetrics.waveform_bars
    || restMetrics?.waveform_bars;
  const activeSource = uploadedMetrics ? 'Uploaded File' : 'Live Microphone';

  const handleToggleSuppression = async () => {
    if (isConnected && !isCapturing) {
      await startCapture();
    }
    toggleSuppression();
  };

  const handleToggleMic = async () => {
    if (isCapturing) {
      stopCapture();
    } else {
      await startCapture();
    }
  };

  const handleRecordAndProcess = (durationSeconds) => {
    clearUploadedMetrics();
    return recordAndProcess(durationSeconds);
  };

  if (loading && !restMetrics) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-slate-400 gap-4">
        <div className="h-7 w-7 border-2 border-[var(--brand-500)] border-t-transparent rounded-full animate-spin"></div>
        <div className="text-[10px] tracking-widest uppercase font-semibold text-slate-500">
          Loading Dashboard...
        </div>
      </div>
    );
  }

  // Combine REST alerts with live WebSocket alerts
  const combinedAlerts = [
    ...(liveMetrics.alerts || []),
    ...alerts,
  ].slice(0, 15);

  return (
    <div className="h-full overflow-y-auto flex flex-col max-w-6xl mx-auto px-6 py-8">
      <DashboardHeader systemStatus={isConnected ? 'online' : systemStatus} />

      <div className="flex flex-col gap-6 pb-12">
        {/* WebSocket error banner */}
        {wsError && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs font-medium">
            ⚠ {wsError}
          </div>
        )}

        {/* KPI Cards — fed by live WS metrics when connected */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 shrink-0">
          <MicrophoneStatusCard status={displayMetrics?.microphone_status} />
          <NoiseLevelCard score={displayMetrics?.noise_score} />
          <VoiceQualityCard clarity={displayMetrics?.voice_clarity} />
          <LatencyCard latency={displayMetrics?.latency} />
        </div>

        {/* Main View: Left side has stack of Upload and Visualizer, Right side has Alerts */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 shrink-0">
          <div className="md:col-span-2 flex flex-col gap-6">
            <div className="flex-1 min-h-fit">
              <AudioUploadCard onUploadSuccess={handleUploadSuccess} onReset={clearUploadedMetrics} />
            </div>
            <div className="min-h-fit">
              <AudioWaveformCard
                bars={activeBars}
                suppressionEnabled={uploadedMetrics ? true : suppressionEnabled}
                isConnected={Boolean(uploadedMetrics) || micIsLive}
                sourceLabel={activeSource}
              />
            </div>
          </div>
          <div className="md:col-span-1 flex flex-col gap-6">
            <div className="flex-1 min-h-[300px]">
              <AlertPanel alerts={combinedAlerts} />
            </div>
          </div>
        </div>

        {/* Noise Suppression Panel — wired to live WebSocket */}
        <NoiseSuppessionPanel
          suppressionEnabled={suppressionEnabled}
          toggleSuppression={handleToggleSuppression}
          playbackEnabled={playbackEnabled}
          togglePlayback={togglePlayback}
          isCapturing={isCapturing}
          toggleMic={handleToggleMic}
          isRecording={isRecording}
          isProcessing={isProcessing}
          beforeUrl={comparisonBeforeUrl}
          afterUrl={comparisonAfterUrl}
          snrBefore={comparisonSnrBefore}
          snrAfter={comparisonSnrAfter}
          recordAndProcess={handleRecordAndProcess}
          resetComparison={() => {
            clearUploadedMetrics();
            resetComparison();
          }}
          noiseClass={displayMetrics.noise_class}
          noiseConfidence={displayMetrics.noise_confidence ?? liveMetrics.noise_confidence ?? 1.0}
          snrDb={displayMetrics.snr_db}
          speechPresence={displayMetrics.speech_presence}
          isConnected={isConnected}
          engine={displayMetrics.engine ?? liveMetrics.engine}
          deepfilternetActive={displayMetrics.deepfilternet_active ?? liveMetrics.deepfilternet_active}
        />

        {/* Cloudinary Gallery */}
        <CloudinaryGallery refreshTrigger={uploadCount} />
      </div>
    </div>
  );
};

export default Dashboard;
