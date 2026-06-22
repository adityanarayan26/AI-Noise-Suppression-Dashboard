/**
 * useAudioWebSocket — custom React hook for real-time audio capture and processing.
 *
 * Responsibilities:
 *  1. Request microphone permission via getUserMedia
 *  2. Capture PCM frames using ScriptProcessorNode
 *  3. Resample frames to 16 kHz Int16 and send over WebSocket with a control byte
 *  4. Receive JSON metrics and base64 suppressed audio from the backend
 *  5. Expose metrics state for the dashboard
 *  6. Play back cleaned audio in real-time when suppression + playback are enabled
 *  7. recordAndProcess(durationSeconds) — single-button recording:
 *       a. Captures raw PCM for durationSeconds
 *       b. Builds a WAV blob
 *       c. POSTs to /api/audio/process
 *       d. Sets beforeUrl (raw) and afterUrl (suppressed) for side-by-side playback
 *
 * Control byte protocol (first byte of every binary message to server):
 *  0x00 = suppression OFF (raw audio)
 *  0x01 = suppression ON  (apply AI pipeline)
 *  0x02 = reset noise profile
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { audioService } from '../services/api';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/audio';

// Target sample rate for the backend DSP
const TARGET_SAMPLE_RATE = 16000;
// Frame size: 1024 samples @ 16 kHz ≈ 64 ms per frame
// (Previously 4096 ≈ 256 ms — reduced for lower interview latency)
const FRAME_SAMPLES = 1024;

export function useAudioWebSocket() {
  // --- Connection state ---
  const [isConnected, setIsConnected] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState(null);

  // --- Live metrics (fed from backend) ---
  const [metrics, setMetrics] = useState({
    microphone_status: 'disconnected',
    noise_score: 0,
    voice_clarity: 0,
    latency: 0,
    audio_quality: 0,
    noise_class: '—',
    noise_confidence: 0,
    noise_level: 0,
    speech_presence: false,
    snr_db: 0,
    waveform_bars: Array(50).fill(0),
    alerts: [],
    suppression_enabled: false,
    engine: 'unknown',
    deepfilternet_active: false,
  });

  // --- Suppression toggle (for live streaming) ---
  const [suppressionEnabled, setSuppressionEnabled] = useState(false);

  // --- Real-time cleaned audio playback ---
  const [playbackEnabled, setPlaybackEnabled] = useState(false);
  const playbackCtxRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const playbackEnabledRef = useRef(false);

  // --- Single-recording comparison state ---
  const [beforeUrl, setBeforeUrl] = useState(null);       // raw audio URL
  const [afterUrl, setAfterUrl] = useState(null);         // suppressed audio URL
  const [isRecording, setIsRecording] = useState(false);  // mic is currently capturing
  const [isProcessing, setIsProcessing] = useState(false); // waiting for /api/audio/process
  const [snrBefore, setSnrBefore] = useState(null);
  const [snrAfter, setSnrAfter] = useState(null);

  // --- Internal refs ---
  const wsRef = useRef(null);
  const audioCtxRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const processorNodeRef = useRef(null);
  const streamRef = useRef(null);
  const pcmBufferRef = useRef([]);        // accumulates Int16 samples for one WS frame
  const recordChunksRef = useRef([]);     // raw frames captured during recordAndProcess
  const isRecordingRef = useRef(false);   // always-fresh mirror of isRecording for closures
  const suppressionRef = useRef(false);   // always-fresh mirror of suppressionEnabled

  // Auto-resume AudioContext on user interaction
  useEffect(() => {
    const resumeAudio = () => {
      if (audioCtxRef.current && audioCtxRef.current.state === 'suspended') {
        audioCtxRef.current.resume();
      }
      if (playbackCtxRef.current && playbackCtxRef.current.state === 'suspended') {
        playbackCtxRef.current.resume();
      }
    };
    // Listen to any interaction to unlock audio
    window.addEventListener('click', resumeAudio);
    window.addEventListener('keydown', resumeAudio);
    return () => {
      window.removeEventListener('click', resumeAudio);
      window.removeEventListener('keydown', resumeAudio);
    };
  }, []);

  // Keep refs in sync with state
  useEffect(() => { suppressionRef.current = suppressionEnabled; }, [suppressionEnabled]);
  useEffect(() => { isRecordingRef.current = isRecording; }, [isRecording]);
  useEffect(() => { playbackEnabledRef.current = playbackEnabled; }, [playbackEnabled]);

  // ─────────────────────────────────────────────────────────────────────────
  // Utility: float32 → Int16 conversion + simple linear resampling
  // ─────────────────────────────────────────────────────────────────────────
  const resampleAndEncode = useCallback((float32Array, sourceSampleRate) => {
    const ratio = sourceSampleRate / TARGET_SAMPLE_RATE;
    const outLen = Math.round(float32Array.length / ratio);
    const int16 = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = Math.min(Math.round(i * ratio), float32Array.length - 1);
      const clamped = Math.max(-1, Math.min(1, float32Array[srcIdx]));
      int16[i] = clamped < 0 ? clamped * 32768 : clamped * 32767;
    }
    return int16;
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Send a PCM frame over WebSocket
  // ─────────────────────────────────────────────────────────────────────────
  const sendFrame = useCallback((int16Array) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const controlByte = suppressionRef.current ? 0x01 : 0x00;
    const payload = new Uint8Array(1 + int16Array.byteLength);
    payload[0] = controlByte;
    payload.set(new Uint8Array(int16Array.buffer), 1);
    wsRef.current.send(payload.buffer);
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Real-time cleaned audio playback
  // ─────────────────────────────────────────────────────────────────────────
  const playCleanedAudio = useCallback((b64String) => {
    try {
      // Lazy-init playback AudioContext
      if (!playbackCtxRef.current) {
        playbackCtxRef.current = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: TARGET_SAMPLE_RATE,
        });
      }
      const ctx = playbackCtxRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume();
        return; // skip this frame; playback will start on next
      }

      // Decode base64 → Int16 → Float32
      const binary = atob(b64String);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const int16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768;
      }

      if (float32.length === 0) return;

      // Create AudioBuffer
      const buffer = ctx.createBuffer(1, float32.length, TARGET_SAMPLE_RATE);
      buffer.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);

      // Schedule gapless playback
      const now = ctx.currentTime;
      if (nextPlayTimeRef.current < now) {
        // First frame or gap — start with a tiny buffer to prevent clicks
        nextPlayTimeRef.current = now + 0.03;
      }
      // Prevent latency buildup: if we're too far ahead, snap back
      if (nextPlayTimeRef.current > now + 0.3) {
        nextPlayTimeRef.current = now + 0.03;
      }

      source.start(nextPlayTimeRef.current);
      nextPlayTimeRef.current += float32.length / TARGET_SAMPLE_RATE;
    } catch (err) {
      // Playback errors shouldn't break the pipeline
      console.warn('Audio playback error:', err);
    }
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Process incoming audio from ScriptProcessorNode
  // ─────────────────────────────────────────────────────────────────────────
  const onAudioProcess = useCallback((float32Samples, sourceSampleRate) => {
    const resampled = resampleAndEncode(float32Samples, sourceSampleRate);
    const buf = pcmBufferRef.current;

    for (let i = 0; i < resampled.length; i++) {
      buf.push(resampled[i]);
      if (buf.length >= FRAME_SAMPLES) {
        const frame = new Int16Array(buf.splice(0, FRAME_SAMPLES));

        // Capture raw frames when a comparison recording is in progress
        if (isRecordingRef.current) {
          recordChunksRef.current.push(frame.slice());
        }

        sendFrame(frame);
      }
    }
  }, [sendFrame, resampleAndEncode]);

  // Keep onAudioProcess in a ref so the ScriptProcessorNode closure always sees latest version
  const onAudioProcessRef = useRef(onAudioProcess);
  useEffect(() => { onAudioProcessRef.current = onAudioProcess; }, [onAudioProcess]);

  // ─────────────────────────────────────────────────────────────────────────
  // Start capturing microphone
  // ─────────────────────────────────────────────────────────────────────────
  const startCapture = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          sampleRate: { ideal: TARGET_SAMPLE_RATE },
        },
      });
      streamRef.current = stream;

      const ctx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: undefined, // use device default; we resample manually
      });
      audioCtxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      sourceNodeRef.current = source;

      const bufferSize = 4096;
      const processor = ctx.createScriptProcessor(bufferSize, 1, 1);
      processorNodeRef.current = processor;

      processor.onaudioprocess = (e) => {
        const float32 = e.inputBuffer.getChannelData(0);
        onAudioProcessRef.current(float32, ctx.sampleRate);
      };

      // Mute the output to prevent speaker feedback while keeping the processor running
      const gainNode = ctx.createGain();
      gainNode.gain.value = 0;

      source.connect(processor);
      processor.connect(gainNode);
      gainNode.connect(ctx.destination);

      setIsCapturing(true);
    } catch (err) {
      setError('Microphone access denied: ' + err.message);
    }
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Stop capturing
  // ─────────────────────────────────────────────────────────────────────────
  const stopCapture = useCallback(() => {
    if (processorNodeRef.current) {
      processorNodeRef.current.disconnect();
      processorNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close();
      playbackCtxRef.current = null;
    }
    pcmBufferRef.current = [];
    nextPlayTimeRef.current = 0;
    setIsCapturing(false);
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // WebSocket connection
  // ─────────────────────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current) return;

    const ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'metrics') {
            setMetrics(prev => ({ ...prev, ...data }));

            // Real-time cleaned audio playback
            if (
              data.suppressed_audio_b64 &&
              playbackEnabledRef.current &&
              suppressionRef.current
            ) {
              playCleanedAudio(data.suppressed_audio_b64);
            }
          }
        } catch {
          // ignore parse errors
        }
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
    };

    ws.onerror = () => {
      setError('WebSocket connection failed. Is the backend running?');
    };
  }, [playCleanedAudio]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    stopCapture();
    setIsConnected(false);
  }, [stopCapture]);

  // ─────────────────────────────────────────────────────────────────────────
  // Auto-connect + capture on mount
  // ─────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    connect();
    return () => disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Start mic capture once WS is connected
  useEffect(() => {
    if (isConnected && !isCapturing) {
      startCapture();
    }
  }, [isConnected]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─────────────────────────────────────────────────────────────────────────
  // Toggle suppression (for live streaming)
  // ─────────────────────────────────────────────────────────────────────────
  const toggleSuppression = useCallback(() => {
    setSuppressionEnabled(prev => !prev);
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Toggle real-time audio playback
  // ─────────────────────────────────────────────────────────────────────────
  const togglePlayback = useCallback(() => {
    setPlaybackEnabled(prev => {
      const next = !prev;
      if (!next && playbackCtxRef.current) {
        // Stop playback — close and reset the context
        playbackCtxRef.current.close();
        playbackCtxRef.current = null;
        nextPlayTimeRef.current = 0;
      }
      return next;
    });
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Single-recording comparison API
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Record `durationSeconds` of raw mic audio, send it to the backend,
   * and populate beforeUrl (raw) + afterUrl (AI-suppressed) for playback.
   */
  const recordAndProcess = useCallback(async (durationSeconds = 5) => {
    if (isRecordingRef.current || !audioCtxRef.current) return;

    // Clear previous results
    setBeforeUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    setAfterUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    setSnrBefore(null);
    setSnrAfter(null);
    recordChunksRef.current = [];

    // --- Phase 1: Record ---
    setIsRecording(true);
    isRecordingRef.current = true;

    await new Promise(resolve => setTimeout(resolve, durationSeconds * 1000));

    setIsRecording(false);
    isRecordingRef.current = false;

    const chunks = recordChunksRef.current.slice();
    recordChunksRef.current = [];

    if (chunks.length === 0) {
      setError('No audio captured. Check microphone connection.');
      return;
    }

    // --- Phase 2: Build WAV blob from raw frames ---
    const totalSamples = chunks.reduce((sum, c) => sum + c.length, 0);
    const combined = new Int16Array(totalSamples);
    let offset = 0;
    for (const chunk of chunks) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    const rawWavBlob = int16ToWavBlob(combined, TARGET_SAMPLE_RATE);

    // --- Phase 3: POST to backend and get both audios back ---
    setIsProcessing(true);
    try {
      const response = await audioService.processAudio(rawWavBlob);
      const { raw_audio_b64, suppressed_audio_b64, snr_before_db, snr_after_db } = response.data;

      // Decode base64 WAV → Blob → Object URL
      const toUrl = (b64) => {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        return URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
      };

      setBeforeUrl(toUrl(raw_audio_b64));
      setAfterUrl(toUrl(suppressed_audio_b64));
      setSnrBefore(snr_before_db);
      setSnrAfter(snr_after_db);
    } catch (err) {
      setError('Processing failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsProcessing(false);
    }
  }, []);

  const resetComparison = useCallback(() => {
    setBeforeUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    setAfterUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    setSnrBefore(null);
    setSnrAfter(null);
    recordChunksRef.current = [];
    setIsRecording(false);
    setIsProcessing(false);
    // Reset noise profile on server
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(new Uint8Array([0x02]).buffer);
    }
  }, []);

  return {
    // Connection
    isConnected,
    isCapturing,
    error,
    connect,
    disconnect,
    // Live metrics
    metrics,
    // Live suppression toggle
    suppressionEnabled,
    toggleSuppression,
    // Real-time audio playback
    playbackEnabled,
    togglePlayback,
    // Single-recording comparison
    isRecording,
    isProcessing,
    beforeUrl,
    afterUrl,
    snrBefore,
    snrAfter,
    recordAndProcess,
    resetComparison,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Helper: encode Int16Array as a WAV file Blob
// ─────────────────────────────────────────────────────────────────────────
function int16ToWavBlob(int16Array, sampleRate) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataLength = int16Array.length * 2;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);            // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeStr(36, 'data');
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < int16Array.length; i++, offset += 2) {
    view.setInt16(offset, int16Array[i], true);
  }

  return new Blob([buffer], { type: 'audio/wav' });
}
