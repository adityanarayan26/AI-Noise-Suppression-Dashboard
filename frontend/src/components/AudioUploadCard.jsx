import React, { useState, useRef } from 'react';
import { audioService, mediaUrl } from '../services/api';

const AudioUploadCard = ({ onUploadSuccess, onReset }) => {
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState(null);
    const [results, setResults] = useState(null);
    const fileInputRef = useRef(null);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setError(null);
            setResults(null);
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        try {
            setUploading(true);
            setError(null);

            const response = await audioService.uploadAudio(file);
            const data = response.data;

            if (data.status === 'success') {
                setResults({
                    noiseType: data.noise_type,
                    noiseConfidence: data.noise_confidence,
                    voiceClarity: data.voice_clarity,
                    noiseScore: data.noise_score,
                    audioQuality: data.audio_quality,
                    speechPresence: data.speech_presence,
                    snrBefore: data.snr_before_db,
                    snrAfter: data.snr_after_db,
                    cleanAudioUrl: mediaUrl(data.clean_audio_url),
                    originalAudioUrl: mediaUrl(data.original_audio_url) || URL.createObjectURL(file)
                });

                // Notify parent dashboard to update general metrics & alerts list
                onUploadSuccess(data);
            } else {
                setError('Processing failed. Please try again.');
            }
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.detail || 'An error occurred during audio processing.');
        } finally {
            setUploading(false);
        }
    };

    const triggerFileSelect = () => {
        fileInputRef.current.click();
    };

    const handleReset = () => {
        setFile(null);
        setResults(null);
        setError(null);
        onReset?.();
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    return (
        <div className="p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col justify-between h-full">
            <div>
                <div className="flex items-center justify-between mb-4 shrink-0">
                    <h3 className="text-sm font-medium text-zinc-900">Audio Processing Hub</h3>
                    <span className="text-[10px] tracking-widest text-zinc-500 uppercase">AI Tool</span>
                </div>

                {/* Drag and Drop Zone */}
                {!results && (
                    <div
                        onClick={triggerFileSelect}
                        className="border-2 border-dashed border-zinc-300 hover:border-zinc-500 transition-colors duration-200 rounded-lg p-6 flex flex-col items-center justify-center cursor-pointer bg-white/40 text-center"
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileChange}
                            accept="audio/*"
                            className="hidden"
                        />
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-8 h-8 text-zinc-500 mb-2">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75V3m0 0L8.25 6.75M12 3l3.75 3.75M19.5 12a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" />
                        </svg>
                        <span className="text-xs font-medium text-zinc-700">
                            {file ? file.name : "Select or Drop Noisy Audio"}
                        </span>
                        <span className="text-[10px] text-zinc-400 mt-1">Supports WAV, MP3, M4A</span>
                    </div>
                )}

                {file && !results && (
                    <button
                        onClick={handleUpload}
                        disabled={uploading}
                        className={`w-full mt-4 py-2 rounded-lg text-xs font-semibold tracking-wide text-white transition-all duration-200 ${uploading ? 'bg-zinc-400 cursor-not-allowed' : 'bg-zinc-900 hover:bg-zinc-800'
                            }`}
                    >
                        {uploading ? 'AI Model processing audio...' : 'Start Suppression & Analysis'}
                    </button>
                )}

                {error && (
                    <div className="mt-3 p-3 bg-red-50 text-red-700 text-xs rounded border border-red-200">
                        {error}
                    </div>
                )}
            </div>

            {/* Audio Players & Results */}
            {results && (
                <div className="mt-4 flex-1 flex flex-col">
                    {/* Classification & metrics strip */}
                    <div className="flex flex-wrap items-center gap-3 mb-4 p-3 bg-white border border-zinc-200 rounded-lg">
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Detected:</span>
                            <span className="px-2 py-0.5 rounded-md text-xs font-medium border bg-indigo-50 text-indigo-700 border-indigo-200">
                                {results.noiseType}
                            </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <span className={`w-1.5 h-1.5 rounded-full ${results.speechPresence ? 'bg-green-500' : 'bg-zinc-300'}`} />
                            <span className="text-[10px] text-zinc-500">{results.speechPresence ? 'Speech' : 'No speech'}</span>
                        </div>
                        <div className="text-[10px] text-zinc-500">
                            Conf. {Math.round((results.noiseConfidence || 0) * 100)}%
                        </div>
                    </div>

                    {/* Metric mini-cards */}
                    <div className="grid grid-cols-3 gap-2 mb-4">
                        <MiniMetric label="Noise" value={results.noiseScore} suffix="%" bad={results.noiseScore > 60} />
                        <MiniMetric label="Clarity" value={results.voiceClarity} suffix="%" good={results.voiceClarity >= 70} />
                        <MiniMetric label="Quality" value={results.audioQuality} suffix="%" good={results.audioQuality >= 70} />
                    </div>

                    {/* Audio players */}
                    <div className="space-y-3 flex-1">
                        <div>
                            <span className="text-[10px] text-zinc-500 block">
                                Original Noisy Audio {results.snrBefore !== null && `(${formatSnr(results.snrBefore)} dB SNR)`}
                            </span>
                            <audio src={results.originalAudioUrl} controls className="w-full h-8 mt-1 scale-95 origin-left" />
                        </div>
                        <div>
                            <span className="text-[10px] text-zinc-500 block">
                                AI Noise-Suppressed Audio {results.snrAfter !== null && `(${formatSnr(results.snrAfter)} dB SNR)`}
                            </span>
                            <audio src={results.cleanAudioUrl} controls className="w-full h-8 mt-1 scale-95 origin-left" />
                        </div>
                    </div>

                    {/* Reset button */}
                    <button
                        onClick={handleReset}
                        className="mt-4 text-xs text-zinc-500 hover:text-zinc-800 underline underline-offset-2 transition-colors self-end"
                    >
                        Upload another file
                    </button>
                </div>
            )}
        </div>
    );
};

const formatSnr = (value) => `${value > 0 ? '+' : ''}${Number(value || 0).toFixed(1)}`;

/** Tiny metric display used inside the upload results */
const MiniMetric = ({ label, value, suffix = '', good, bad }) => {
    const color = good ? 'text-green-600' : bad ? 'text-red-500' : 'text-amber-600';
    return (
        <div className="p-2 bg-zinc-50 border border-zinc-200 rounded-lg text-center">
            <div className="text-[9px] text-zinc-400 uppercase tracking-widest">{label}</div>
            <div className={`text-sm font-bold tabular-nums ${color}`}>{value}{suffix}</div>
        </div>
    );
};

export default AudioUploadCard;

