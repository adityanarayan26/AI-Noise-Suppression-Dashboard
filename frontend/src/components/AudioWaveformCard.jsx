import React, { useEffect, useRef, useState } from 'react';
import { audioService } from '../services/api';

const AudioWaveformCard = ({ onUploadSuccess }) => {
  const [isListening, setIsListening] = useState(false);
  const [isSuppressing, setIsSuppressing] = useState(false);
  const [recordingState, setRecordingState] = useState('idle'); // 'idle', 'recording', 'processing', 'success', 'error'
  
  // Recorded Audio URLs and Results
  const [beforeAudioUrl, setBeforeAudioUrl] = useState(null);
  const [afterAudioUrl, setAfterAudioUrl] = useState(null);
  const [noiseClassification, setNoiseClassification] = useState(null);
  const [voiceClarityScore, setVoiceClarityScore] = useState(null);
  const [noiseLevelScore, setNoiseLevelScore] = useState(null);
  const [audioQualityScore, setAudioQualityScore] = useState(null);
  const [uploadError, setUploadError] = useState(null);

  const canvasRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const animationRef = useRef(null);
  
  // WebSockets and Streaming refs
  const socketRef = useRef(null);
  const processorRef = useRef(null);
  const nextPlayTimeRef = useRef(0);

  // Recording Buffer Ref
  const recordingSamplesRef = useRef([]);

  // WAV encoder helper function
  const bufferToWav = (buffer, sampleRate) => {
    const bufferLength = buffer.length;
    const wavBuffer = new ArrayBuffer(44 + bufferLength * 2);
    const view = new DataView(wavBuffer);

    const writeString = (view, offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };

    /* RIFF identifier */
    writeString(view, 0, 'RIFF');
    /* file length */
    view.setUint32(4, 36 + bufferLength * 2, true);
    /* RIFF type */
    writeString(view, 8, 'WAVE');
    /* format chunk identifier */
    writeString(view, 12, 'fmt ');
    /* format chunk length */
    view.setUint32(16, 16, true);
    /* sample format (raw PCM) */
    view.setUint16(20, 1, true);
    /* channel count (mono) */
    view.setUint16(22, 1, true);
    /* sample rate */
    view.setUint32(24, sampleRate, true);
    /* byte rate (sample rate * block align) */
    view.setUint32(28, sampleRate * 2, true);
    /* block align (channel count * bytes per sample) */
    view.setUint16(32, 2, true);
    /* bits per sample */
    view.setUint16(34, 16, true);
    /* data chunk identifier */
    writeString(view, 36, 'data');
    /* data chunk length */
    view.setUint32(40, bufferLength * 2, true);

    // Write PCM audio samples (convert Float32 to Int16 PCM)
    let offset = 44;
    for (let i = 0; i < bufferLength; i++, offset += 2) {
      let s = Math.max(-1, Math.min(1, buffer[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }

    return new Blob([view], { type: 'audio/wav' });
  };

  // Start live monitoring or real-time streaming
  const startLiveMonitor = async (shouldSuppress = false) => {
    try {
      // Clean up any existing instances first
      stopListening();
      setUploadError(null);

      // 1. Get microphone stream
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 2. Set up Web Audio API context at 16000Hz (auto-resampled)
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;
      nextPlayTimeRef.current = audioCtx.currentTime;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);

      if (shouldSuppress) {
        // --- WebSocket Streaming suppression setup ---
        const ws = new WebSocket('ws://localhost:8000/audio/stream');
        ws.binaryType = 'arraybuffer';
        socketRef.current = ws;

        ws.onopen = () => {
          console.log('Connected to real-time suppression WebSocket');
          
          // Create script processor to read mic chunks (buffer size 4096 frames = 256ms chunk size)
          const processor = audioCtx.createScriptProcessor(4096, 1, 1);
          processorRef.current = processor;

          source.connect(processor);
          processor.connect(audioCtx.destination);

          processor.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(inputData.buffer);
            }
          };
        };

        ws.onmessage = (e) => {
          const cleanBuffer = e.data;
          const cleanData = new Float32Array(cleanBuffer);

          // Build audio source node from returned clean data
          const playBuffer = audioCtx.createBuffer(1, cleanData.length, 16000);
          playBuffer.getChannelData(0).set(cleanData);

          const bufferSource = audioCtx.createBufferSource();
          bufferSource.buffer = playBuffer;

          // Connect to analyser (for drawing cleaned waveform) and speakers
          bufferSource.connect(analyser);
          analyser.connect(audioCtx.destination);

          // Queue playback continuously to prevent gaps/clicks
          if (nextPlayTimeRef.current < audioCtx.currentTime) {
            nextPlayTimeRef.current = audioCtx.currentTime;
          }
          bufferSource.start(nextPlayTimeRef.current);
          nextPlayTimeRef.current += playBuffer.duration;
        };

        ws.onerror = (err) => {
          console.error('WebSocket Error:', err);
        };

        ws.onclose = () => {
          console.log('Suppression WebSocket closed');
        };

        setIsSuppressing(true);
      } else {
        // --- Standard raw microphone setup ---
        source.connect(analyser);
        setIsSuppressing(false);
      }

      setIsListening(true);
      drawWaveform();
    } catch (err) {
      console.error('Error accessing microphone for live monitor:', err);
      setUploadError('Could not access microphone. Please check browser permissions.');
      stopListening();
    }
  };

  const toggleSuppressionLiveState = (enable) => {
    if (enable) {
      if (socketRef.current) return; // already streaming
      
      const audioCtx = audioContextRef.current;
      if (!audioCtx) return;

      const ws = new WebSocket('ws://localhost:8000/audio/stream');
      ws.binaryType = 'arraybuffer';
      socketRef.current = ws;

      ws.onopen = () => {
        console.log('Suppression enabled during active session');
      };

      ws.onmessage = (e) => {
        const cleanBuffer = e.data;
        const cleanData = new Float32Array(cleanBuffer);

        const playBuffer = audioCtx.createBuffer(1, cleanData.length, 16000);
        playBuffer.getChannelData(0).set(cleanData);

        const bufferSource = audioCtx.createBufferSource();
        bufferSource.buffer = playBuffer;

        // Connect to analyser and speakers
        bufferSource.connect(analyserRef.current);
        analyserRef.current.connect(audioCtx.destination);

        if (nextPlayTimeRef.current < audioCtx.currentTime) {
          nextPlayTimeRef.current = audioCtx.currentTime;
        }
        bufferSource.start(nextPlayTimeRef.current);
        nextPlayTimeRef.current += playBuffer.duration;
      };
    } else {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    }
  };

  const startRecording = async () => {
    try {
      stopListening();
      setRecordingState('recording');
      setUploadError(null);
      
      // 1. Get microphone stream
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 2. Set up Web Audio API context at 16000Hz (auto-resampled)
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;
      nextPlayTimeRef.current = audioCtx.currentTime;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      // Collect audio chunks in memory
      recordingSamplesRef.current = [];
      
      // Create script processor to read mic chunks (buffer size 4096 frames = 256ms chunk)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      source.connect(processor);
      processor.connect(audioCtx.destination);

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        recordingSamplesRef.current.push(new Float32Array(inputData));
        
        // Stream to WebSocket if suppression is active
        if (isSuppressing && socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(inputData.buffer);
        }
      };

      setIsListening(true);
      drawWaveform();

      if (isSuppressing) {
        toggleSuppressionLiveState(true);
      }
    } catch (err) {
      console.error('Error starting recording:', err);
      setUploadError('Could not access microphone. Please check permissions.');
      setRecordingState('idle');
    }
  };

  const stopRecording = async () => {
    if (recordingState !== 'recording') return;
    setRecordingState('processing');

    try {
      // 1. Terminate all capture nodes immediately
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setIsListening(false);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }

      // 2. Concatenate samples
      const chunks = recordingSamplesRef.current;
      if (chunks.length === 0) {
        throw new Error("No audio was recorded.");
      }
      const totalLength = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
      const flatBuffer = new Float32Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        flatBuffer.set(chunk, offset);
        offset += chunk.length;
      }

      // 3. Convert to WAV Blob
      const wavBlob = bufferToWav(flatBuffer, 16000);
      const audioFile = new File([wavBlob], `recording_${Date.now()}.wav`, { type: 'audio/wav' });

      // 4. Send to backend
      const response = await audioService.uploadAudio(audioFile);
      const data = response.data;

      if (data.status === 'success') {
        const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        setBeforeAudioUrl(URL.createObjectURL(wavBlob));
        setAfterAudioUrl(`${API_BASE_URL}${data.clean_audio_url}`);
        setNoiseClassification(data.noise_type);
        setVoiceClarityScore(data.voice_clarity);
        setNoiseLevelScore(data.noise_score);
        setAudioQualityScore(data.audio_quality);
        setRecordingState('success');

        // Update dashboard metrics
        if (onUploadSuccess) {
          onUploadSuccess(data);
        }
      } else {
        throw new Error("Processing failed on server.");
      }
    } catch (err) {
      console.error('Error uploading recording:', err);
      setUploadError(err.response?.data?.detail || err.message || 'An error occurred during audio processing.');
      setRecordingState('error');
    }
  };

  const stopListening = () => {
    // Stop recording visualizer loop
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }
    // Stop recording script processor
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    // Close WebSocket
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    // Stop microphone stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    // Close Audio Context
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    
    setIsListening(false);
    setIsSuppressing(false);
    clearCanvas();
  };

  const toggleMic = () => {
    if (isListening) {
      stopListening();
    } else {
      startLiveMonitor(isSuppressing);
    }
  };

  const toggleSuppression = () => {
    const nextSuppression = !isSuppressing;
    setIsSuppressing(nextSuppression);
    if (recordingState === 'recording') {
      toggleSuppressionLiveState(nextSuppression);
    } else if (isListening && recordingState === 'idle') {
      stopListening();
      startLiveMonitor(nextSuppression);
    }
  };

  const clearRecordings = () => {
    setBeforeAudioUrl(null);
    setAfterAudioUrl(null);
    setNoiseClassification(null);
    setVoiceClarityScore(null);
    setNoiseLevelScore(null);
    setAudioQualityScore(null);
    setRecordingState('idle');
    setUploadError(null);
  };

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw empty baseline
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#d4d4d8'; // zinc-300
    ctx.beginPath();
    ctx.moveTo(0, canvas.height / 2);
    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();
  };

  const drawWaveform = () => {
    const canvas = canvasRef.current;
    if (!canvas || !analyserRef.current) return;

    const ctx = canvas.getContext('2d');
    const bufferLength = analyserRef.current.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animationRef.current = requestAnimationFrame(draw);
      analyserRef.current.getByteFrequencyData(dataArray);

      // Smooth background
      ctx.fillStyle = '#f4f4f5'; // zinc-100
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw horizontal grid lines
      ctx.strokeStyle = '#e4e4e7'; // zinc-200
      ctx.lineWidth = 1;
      const gridCount = 4;
      for (let i = 1; i < gridCount; i++) {
        const y = (canvas.height / gridCount) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // Draw vertical frequency bars (35 bars)
      const barCount = 35;
      const gap = 6;
      const barWidth = (canvas.width - (barCount - 1) * gap) / barCount;

      for (let i = 0; i < barCount; i++) {
        // Target mid-low frequency ranges (speech)
        const binIndex = Math.floor(4 + (i / barCount) * (bufferLength * 0.5));
        const value = dataArray[binIndex] || 0;

        // Map 0-255 to height
        const percent = value / 255;
        const maxBarHeight = canvas.height * 0.75;
        const barHeight = Math.max(3, percent * maxBarHeight);

        const x = i * (barWidth + gap);
        const y = (canvas.height - barHeight) / 2; // Center bars vertically

        // Color matching states
        let barColor = '#d4d4d8'; // Zinc-300 default (inactive)
        
        if (isListening) {
          if (recordingState === 'recording') {
            barColor = i % 2 === 0 ? '#f97316' : '#ef4444'; // Orange/Red pulse
          } else if (isSuppressing) {
            barColor = i % 2 === 0 ? '#10b981' : '#06b6d4'; // Emerald/Cyan suppression
          } else {
            barColor = i % 2 === 0 ? '#6366f1' : '#3b82f6'; // Indigo/Blue normal
          }
        }

        ctx.fillStyle = barColor;

        const radius = Math.min(barWidth / 2, 4);
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, radius);
        ctx.fill();
      }
    };

    draw();
  };

  useEffect(() => {
    clearCanvas();
    return () => {
      stopListening();
    };
  }, []);

  return (
    <div className="h-full p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between mb-4 shrink-0">
          <div>
            <h3 className="text-sm font-medium text-zinc-900">Live Activity</h3>
            <span className="text-[10px] text-zinc-500">
              {recordingState === 'recording'
                ? "Recording microphone input..."
                : isSuppressing 
                  ? "Real-time spectral suppression active" 
                  : "Microphone analysis"}
            </span>
          </div>
          
          {/* Status Badge */}
          <div className="flex items-center gap-2">
            {recordingState === 'recording' && (
              <span className="px-2 py-0.5 rounded bg-red-100 text-red-700 text-[10px] font-bold uppercase tracking-wider animate-pulse flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-red-600"></span>
                RECORDING
              </span>
            )}
            {isListening && recordingState !== 'recording' && (
              <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-600 animate-ping"></span>
                LIVE MONITOR
              </span>
            )}
          </div>
        </div>
        
        {/* Canvas Display */}
        <div className="h-[90px] rounded-lg overflow-hidden border border-zinc-200 relative bg-zinc-100">
          <canvas 
            ref={canvasRef} 
            width={500} 
            height={130} 
            className="w-full h-full object-cover" 
          />
          
          {/* Overlays */}
          {recordingState === 'processing' && (
            <div className="absolute inset-0 bg-white/80 flex flex-col items-center justify-center border border-zinc-200 rounded-lg">
              <div className="h-6 w-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mb-2 flex-shrink-0"></div>
              <span className="text-indigo-800 font-semibold text-xs tracking-wider animate-pulse">
                AI model is processing audio...
              </span>
            </div>
          )}
        </div>

        {/* Controls Layout */}
        <div className="mt-4 flex gap-2">
          {/* Main Record Action */}
          {recordingState === 'recording' ? (
            <button
              onClick={stopRecording}
              className="flex-1 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-white font-semibold text-xs tracking-wide transition-all duration-200 shadow-sm flex items-center justify-center gap-1"
            >
              ⏹️ Stop & Process Audio
            </button>
          ) : (
            <button
              onClick={startRecording}
              disabled={recordingState === 'processing'}
              className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold text-xs tracking-wide transition-all duration-200 shadow-sm flex items-center justify-center gap-1 disabled:opacity-50"
            >
              🎙️ Record Audio Session
            </button>
          )}

          {/* Mic Toggle Button */}
          {recordingState === 'idle' && (
            <button
              onClick={toggleMic}
              className={`px-3 py-2 rounded-lg border text-xs font-semibold tracking-wide transition-all duration-200 ${
                isListening
                  ? 'bg-blue-600 border-blue-700 text-white hover:bg-blue-500'
                  : 'bg-white border-zinc-300 text-zinc-700 hover:bg-zinc-50'
              }`}
              title="Toggle live microphone stream"
            >
              {isListening ? 'Mic: ON' : 'Mic: OFF'}
            </button>
          )}

          {/* Suppression Toggle Button */}
          {(recordingState === 'idle' || recordingState === 'recording') && (
            <button
              onClick={toggleSuppression}
              className={`px-3 py-2 rounded-lg border text-xs font-semibold tracking-wide transition-all duration-200 ${
                isSuppressing
                  ? 'bg-emerald-600 border-emerald-700 text-white hover:bg-emerald-500'
                  : 'bg-white border-zinc-300 text-zinc-700 hover:bg-zinc-50'
              }`}
              title="Toggle AI spectral suppression filtering"
            >
              {isSuppressing ? 'Suppression: ON' : 'Suppression: OFF'}
            </button>
          )}
        </div>

        {uploadError && (
          <div className="mt-3 p-3 bg-red-50 text-red-700 text-[11px] rounded border border-red-200">
            ⚠️ {uploadError}
          </div>
        )}
      </div>
      
      {/* Side-by-Side Comparison Players (Available on Success) */}
      {recordingState === 'success' && (beforeAudioUrl || afterAudioUrl) && (
        <div className="mt-4 border-t border-zinc-200 pt-4 shrink-0">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold block">Processed Results</span>
              {noiseClassification && (
                <span className="text-xs text-zinc-700">
                  Dominant Noise: <span className="font-semibold text-indigo-600">{noiseClassification}</span>
                </span>
              )}
            </div>
            <button
              onClick={clearRecordings}
              className="text-[10px] text-zinc-500 hover:text-red-600 font-medium underline"
            >
              Clear
            </button>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-3 bg-white border border-zinc-200 rounded-lg shadow-sm">
              <span className="text-[10px] font-semibold text-orange-600 uppercase tracking-wider block mb-1">Before (Original)</span>
              {beforeAudioUrl ? (
                <audio src={beforeAudioUrl} controls className="w-full h-8 scale-95 origin-left" />
              ) : (
                <div className="h-8 flex items-center justify-center text-[10px] text-zinc-400 italic">No audio</div>
              )}
            </div>
            <div className="p-3 bg-white border border-zinc-200 rounded-lg shadow-sm">
              <span className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wider block mb-1">After (Suppressed Voice)</span>
              {afterAudioUrl ? (
                <audio src={afterAudioUrl} controls className="w-full h-8 scale-95 origin-left" />
              ) : (
                <div className="h-8 flex items-center justify-center text-[10px] text-zinc-400 italic">No audio</div>
              )}
            </div>
          </div>
        </div>
      )}

      {isSuppressing && (
        <div className="mt-2 text-[10px] text-zinc-500 text-center animate-pulse">
          🎧 Use headphones to prevent microphone feedback loops while playing back suppressed audio.
        </div>
      )}
    </div>
  );
};

export default AudioWaveformCard;
