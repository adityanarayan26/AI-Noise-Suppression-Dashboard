import React, { useState, useRef } from 'react';
import { audioService } from '../services/api';

const AudioUploadCard = ({ onUploadSuccess }) => {
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
                    voiceClarity: data.voice_clarity,
                    noiseScore: data.noise_score,
                    audioQuality: data.audio_quality,
                    cleanAudioUrl: `http://localhost:8000${data.clean_audio_url}`,
                    originalAudioUrl: URL.createObjectURL(file)
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

    return (
        <div className="p-6 border border-zinc-300 rounded-xl bg-zinc-100/50 flex flex-col justify-between h-full">
            <div>
                <div className="flex items-center justify-between mb-4 shrink-0">
                    <h3 className="text-sm font-medium text-zinc-900">Audio Processing Hub</h3>
                    <span className="text-[10px] tracking-widest text-zinc-500 uppercase">AI Tool</span>
                </div>

                {/* Drag and Drop Zone */}
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
                <div className="mt-6 border-t border-zinc-200 pt-4 flex-1 flex flex-col justify-end">
                    <div className="mb-3">
                        <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">AI Classification</span>
                        <span className="text-sm font-semibold text-zinc-800">Dominant Noise: <span className="text-indigo-600">{results.noiseType}</span></span>
                    </div>

                    <div className="space-y-3">
                        <div>
                            <span className="text-[10px] text-zinc-500 block">Original Noisy Audio</span>
                            <audio src={results.originalAudioUrl} controls className="w-full h-8 mt-1 scale-95 origin-left" />
                        </div>
                        <div>
                            <span className="text-[10px] text-zinc-500 block">Cleaned Speech (ConvTasNet Output)</span>
                            <audio src={results.cleanAudioUrl} controls className="w-full h-8 mt-1 scale-95 origin-left" />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AudioUploadCard;
