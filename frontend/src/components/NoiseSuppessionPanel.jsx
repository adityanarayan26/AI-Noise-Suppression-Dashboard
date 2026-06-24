import React, { useState, useEffect, useRef } from 'react';

/**
 * NoiseSuppessionPanel
 *
 * Single-recording before/after comparison:
 *  1. User clicks "Record" — mic captures for RECORD_DURATION_S seconds
 *  2. Recording is sent to the backend AI pipeline
 *  3. Both raw and AI-suppressed audio are displayed side-by-side
 *
 * Props:
 *   suppressionEnabled   {boolean}
 *   toggleSuppression    {function}
 *   playbackEnabled      {boolean}  — real-time cleaned audio playback
 *   togglePlayback       {function}
 *   isRecording          {boolean}   — mic is currently capturing
 *   isProcessing         {boolean}   — waiting for backend response
 *   beforeUrl            {string|null}
 *   afterUrl             {string|null}
 *   snrBefore            {number|null}
 *   snrAfter             {number|null}
 *   recordAndProcess     {function(durationSeconds)}
 *   resetComparison      {function}
 *   noiseClass           {string}
 *   noiseConfidence      {number}
 *   snrDb                {number}
 *   speechPresence       {boolean}
 *   isConnected          {boolean}
 *   engine               {string}    — 'deepfilternet' or 'spectral_subtraction'
 *   deepfilternetActive  {boolean}
 */

const RECORD_DURATION_S = 5;

const NoiseSuppessionPanel = ({
  suppressionEnabled,
  toggleSuppression,
  playbackEnabled,
  togglePlayback,
  isCapturing,
  toggleMic,
  isRecording,
  isProcessing,
  beforeUrl,
  afterUrl,
  snrBefore,
  snrAfter,
  recordAndProcess,
  resetComparison,
  noiseClass,
  noiseConfidence,
  snrDb,
  speechPresence,
  isConnected,
  engine,
  deepfilternetActive,
}) => {
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef(null);

  const handleRecord = () => {
    if (isRecording || isProcessing || !isConnected || !isCapturing) return;
    setCountdown(RECORD_DURATION_S);

    // Tick the countdown display
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    recordAndProcess(RECORD_DURATION_S);
  };

  useEffect(() => () => clearInterval(timerRef.current), []);

  const noiseClassColor = {
    'Fan Noise':               'bg-blue-100 text-blue-700 border-blue-300',
    'Traffic Noise':           'bg-orange-100 text-orange-700 border-orange-300',
    'Keyboard Typing':         'bg-purple-100 text-purple-700 border-purple-300',
    'Background Conversation': 'bg-rose-100 text-rose-700 border-rose-300',
    'AC Noise':                'bg-cyan-100 text-cyan-700 border-cyan-300',
    'Clean / No Noise':        'bg-green-100 text-green-700 border-green-300',
    'Other':                   'bg-zinc-100 text-zinc-700 border-zinc-300',
  };
  const badgeClass = noiseClassColor[noiseClass] || noiseClassColor['Other'];

  const hasResults = beforeUrl && afterUrl;

  // Engine display
  const engineLabel = deepfilternetActive ? 'DeepFilterNet' : 'Spectral Subtraction';
  const engineColor = deepfilternetActive
    ? 'bg-[var(--brand-100)] text-[var(--brand-700)] border-[var(--brand-300)]'
    : 'bg-amber-100 text-amber-700 border-amber-300';

  return (
    <div className="shrink-0 mt-6 border border-[var(--panel-border)] rounded-xl bg-[var(--panel-bg)] backdrop-blur-sm p-6 shadow-[0_14px_40px_rgba(0,135,64,0.08)]">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h3 className="text-sm font-medium text-[var(--app-text)]">Noise Suppression Comparison</h3>
          <p className="text-xs text-[var(--brand-700)] mt-0.5">
            Record once — hear the difference before and after AI processing
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Engine badge */}
          <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest border ${engineColor}`}>
            ⚙ {engineLabel}
          </span>

          {/* Live indicator */}
          <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider ${isConnected ? 'text-[var(--brand-700)]' : 'text-red-500'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-[var(--brand-500)] animate-pulse' : 'bg-red-500'}`} />
            {isConnected ? 'Live' : 'Offline'}
          </span>

          <button
            id="mic-toggle-btn"
            onClick={toggleMic}
            disabled={!isConnected}
            className={`
              relative inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold
              uppercase tracking-widest border transition-all duration-200
              ${isCapturing
                ? 'bg-[var(--brand-50)] text-[var(--brand-700)] border-[var(--brand-300)] hover:bg-[var(--brand-100)]'
                : 'bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50'}
              disabled:opacity-40 disabled:cursor-not-allowed
            `}
          >
            <span className={`w-2 h-2 rounded-full ${isCapturing ? 'bg-[var(--brand-500)] animate-pulse' : 'bg-zinc-400'}`} />
            Mic {isCapturing ? 'ON' : 'OFF'}
          </button>

          {/* Suppression toggle (controls live-stream mode only) */}
          <button
            id="suppression-toggle-btn"
            onClick={toggleSuppression}
            disabled={!isConnected}
            className={`
              relative inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold
              uppercase tracking-widest border transition-all duration-200
              ${suppressionEnabled
                ? 'bg-[var(--brand-500)] text-white border-[var(--brand-500)] hover:bg-[var(--brand-600)]'
                : 'bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50'}
              disabled:opacity-40 disabled:cursor-not-allowed
            `}
          >
            <span className={`w-2 h-2 rounded-full ${suppressionEnabled ? 'bg-[var(--brand-200)]' : 'bg-zinc-400'}`} />
            Suppression {suppressionEnabled ? 'ON' : 'OFF'}
          </button>

          {/* Playback toggle — listen to cleaned audio in real-time */}
          {suppressionEnabled && (
            <button
              id="playback-toggle-btn"
              onClick={togglePlayback}
              disabled={!isConnected}
              className={`
                relative inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold
                uppercase tracking-widest border transition-all duration-200
                ${playbackEnabled
                  ? 'bg-[var(--brand-700)] text-white border-[var(--brand-700)] hover:bg-[var(--brand-600)]'
                  : 'bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50'}
                disabled:opacity-40 disabled:cursor-not-allowed
              `}
              title="Listen to the AI-cleaned audio through your speakers (use headphones to avoid feedback)"
            >
              {playbackEnabled ? '🔊' : '🔇'}
              {playbackEnabled ? 'Listening' : 'Listen'}
            </button>
          )}
        </div>
      </div>

      {/* Headphone warning when playback is active */}
      {playbackEnabled && suppressionEnabled && (
        <div className="mb-4 p-2.5 rounded-lg bg-[var(--brand-50)] border border-[var(--brand-200)] text-[var(--brand-700)] text-xs font-medium flex items-center gap-2">
          <span>🎧</span>
          <span>Use headphones to avoid audio feedback. You're hearing the AI-cleaned audio in real-time.</span>
        </div>
      )}

      {/* ── AI Analysis strip ── */}
      <div className="flex flex-wrap items-center gap-4 mb-6 p-3 bg-white border border-zinc-200 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500 uppercase tracking-wider">Detected:</span>
          <span className={`px-2.5 py-1 rounded-md text-xs font-medium border ${badgeClass}`}>
            {noiseClass || '—'}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-1 min-w-[120px]">
          <span className="text-xs text-zinc-500 whitespace-nowrap">Conf.</span>
          <div className="flex-1 h-1.5 bg-zinc-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-zinc-700 rounded-full transition-all duration-500"
              style={{ width: `${Math.round((noiseConfidence || 0) * 100)}%` }}
            />
          </div>
          <span className="text-xs text-zinc-600 w-8 text-right">
            {Math.round((noiseConfidence || 0) * 100)}%
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-zinc-500 uppercase tracking-wider">SNR:</span>
          <span className={`text-xs font-semibold ${snrDb > 15 ? 'text-green-600' : snrDb > 5 ? 'text-amber-600' : 'text-red-500'}`}>
            {snrDb > 0 ? '+' : ''}{(snrDb || 0).toFixed(1)} dB
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${speechPresence ? 'bg-green-500' : 'bg-zinc-300'}`} />
          <span className="text-xs text-zinc-500">{speechPresence ? 'Speech detected' : 'No speech'}</span>
        </div>
      </div>

      {/* ── Record button + state ── */}
      <div className="flex flex-col items-center gap-4 mb-6">
        {/* The single Record button */}
        <button
          id="record-btn"
          onClick={handleRecord}
          disabled={!isConnected || !isCapturing || isRecording || isProcessing}
          className={`
            flex items-center gap-3 px-8 py-3 rounded-xl text-sm font-semibold
            uppercase tracking-widest border-2 transition-all duration-200
            ${isRecording
              ? 'bg-red-50 border-red-400 text-red-600 cursor-not-allowed'
              : isProcessing
                ? 'bg-zinc-100 border-zinc-300 text-zinc-400 cursor-not-allowed'
                : 'bg-[var(--brand-500)] border-[var(--brand-500)] text-white hover:bg-[var(--brand-600)] active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed'}
          `}
        >
          {isRecording ? (
            <>
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
              Recording… {countdown}s remaining
            </>
          ) : isProcessing ? (
            <>
              <Spinner />
              Applying AI suppression…
            </>
          ) : (
            <>
              <span className="w-2.5 h-2.5 rounded-full bg-white" />
              Record {RECORD_DURATION_S}s Sample
            </>
          )}
        </button>

        {isConnected && !isCapturing && !isRecording && !isProcessing && (
          <p className="text-xs text-amber-600 text-center">
            Turn Mic ON to classify a 5s sample and animate live activity.
          </p>
        )}

        {!hasResults && !isRecording && !isProcessing && (
          <p className="text-xs text-zinc-400 text-center">
            Click Record — your voice will be captured, then processed by the AI pipeline
          </p>
        )}
      </div>

      {/* ── Side-by-side audio players (shown after processing) ── */}
      {hasResults && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Before: raw */}
          <AudioCard
            id="before"
            label="Before"
            labelClass="bg-zinc-200 text-zinc-600"
            cardClass="border-zinc-300"
            description="Raw microphone — unprocessed"
            audioUrl={beforeUrl}
            snrDb={snrBefore}
          />

          {/* After: AI suppressed */}
          <AudioCard
            id="after"
            label="After"
            labelClass="bg-[var(--brand-500)] text-white"
            cardClass="border-[var(--brand-500)]"
            description="AI noise suppression applied"
            audioUrl={afterUrl}
            snrDb={snrAfter}
          />
        </div>
      )}

      {/* ── Reset ── */}
      {hasResults && !isRecording && !isProcessing && (
        <div className="mt-4 flex justify-end">
          <button
            id="reset-comparison-btn"
            onClick={resetComparison}
            className="text-xs text-[var(--brand-700)] hover:text-[var(--brand-900)] underline underline-offset-2 transition-colors"
          >
            Clear recordings &amp; reset noise profile
          </button>
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────
// AudioCard — one side of the comparison
// ─────────────────────────────────────────────────────────────────────────
const AudioCard = ({ id, label, labelClass, cardClass, description, audioUrl, snrDb }) => (
  <div className={`flex flex-col gap-3 p-4 rounded-lg bg-white border ${cardClass}`}>
    <div className="flex items-center justify-between">
      <div>
        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest mb-1 ${labelClass}`}>
          {label}
        </span>
        <p className="text-xs text-zinc-500">{description}</p>
      </div>

      {snrDb !== null && snrDb !== undefined && (
        <div className="text-right">
          <p className="text-[10px] text-zinc-400 uppercase tracking-wider">SNR</p>
          <p className={`text-sm font-semibold ${snrDb > 15 ? 'text-green-600' : snrDb > 5 ? 'text-amber-600' : 'text-red-500'}`}>
            {snrDb > 0 ? '+' : ''}{snrDb.toFixed(1)} dB
          </p>
        </div>
      )}
    </div>

    <audio
      id={`audio-player-${id}`}
      controls
      src={audioUrl}
      className="w-full h-8 rounded"
      style={{ accentColor: '#008740' }}
    />
  </div>
);

// ─────────────────────────────────────────────────────────────────────────
// Spinner SVG
// ─────────────────────────────────────────────────────────────────────────
const Spinner = () => (
  <svg className="animate-spin w-4 h-4 text-zinc-500" viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
  </svg>
);

export default NoiseSuppessionPanel;
