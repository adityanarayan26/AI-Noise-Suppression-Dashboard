import React, { useState, useEffect } from 'react';
import { audioService } from '../services/api';

import AudioPlayer from 'react-h5-audio-player';
import 'react-h5-audio-player/lib/styles.css';
import '../audioPlayer.css';



const CloudinaryGallery = ({ refreshTrigger }) => {
    const [files, setFiles] = useState({ before: [], after: [] });
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('before'); // 'before' or 'after'

    useEffect(() => {
        const fetchFiles = async () => {
            try {
                setLoading(true);
                const response = await audioService.getCloudinaryFiles();
                setFiles(response.data);
            } catch (error) {
                console.error("Failed to fetch Cloudinary files", error);
            } finally {
                setLoading(false);
            }
        };

        fetchFiles();
    }, [refreshTrigger]);

    if (loading) {
        return (
            <div className="flex justify-center items-center p-8 text-sm text-zinc-500">
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-zinc-800" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Loading Cloudinary Audio Files...
            </div>
        );
    }

    const currentFiles = activeTab === 'before' ? files.before : files.after;

    const formatDate = (isoDate) => {
        return new Date(isoDate).toLocaleString("en-IN", {
            dateStyle: "medium",
            timeStyle: "short",
        });
    };

    return (
        <div className="mt-8 border-t border-zinc-300 pt-8">
            <h2 className="text-lg font-medium text-zinc-900 mb-6">Cloudinary Audio Gallery</h2>

            {/* Tabs */}
            <div className="flex space-x-2 border-b border-zinc-200 mb-6">
                <button
                    onClick={() => setActiveTab('before')}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'before'
                        ? 'border-zinc-900 text-zinc-900'
                        : 'border-transparent text-zinc-500 hover:text-zinc-700 hover:border-zinc-300'
                        }`}
                >
                    Before Suppression (Raw)
                </button>
                <button
                    onClick={() => setActiveTab('after')}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'after'
                        ? 'border-zinc-900 text-zinc-900'
                        : 'border-transparent text-zinc-500 hover:text-zinc-700 hover:border-zinc-300'
                        }`}
                >
                    After Suppression (Cleaned)
                </button>
            </div>

            {/* Tab Content */}
            <div className="p-6 border border-zinc-300 rounded-xl bg-zinc-50 min-h-[200px]">
                {currentFiles.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-zinc-500 py-8">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-8 h-8 mb-2 opacity-50">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75V3m0 0L8.25 6.75M12 3l3.75 3.75M19.5 12a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" />
                        </svg>
                        <p className="text-sm">No audio files found in this folder.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-96 overflow-y-auto pr-2">
                        {currentFiles.map((file, idx) => (
                            <div
                                key={idx}
                                className="bg-white rounded-xl border border-zinc-200 shadow-sm p-5"
                            >
                                <div className="flex justify-between items-start mb-4">

                                    <div>
                                        <p className="font-medium text-zinc-800 truncate max-w-xs">
                                            {file.id.split("/").pop()}
                                        </p>

                                        <p className="text-xs text-zinc-500 mt-1">

                                            Uploaded • {formatDate(file.created_at)}
                                        </p>
                                    </div>

                                    <span className="px-2 py-1 rounded-full bg-green-100 text-green-700 text-xs font-medium">
                                        {file.format?.toUpperCase() || "AUDIO"}
                                    </span>

                                </div>
                                <AudioPlayer
                                    src={file.url}
                                    showJumpControls={false}
                                    autoPlayAfterSrcChange={false}
                                    customAdditionalControls={[]}
                                    customVolumeControls={['VOLUME']}
                                    layout="horizontal"
                                    className="w-full"
                                />
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default CloudinaryGallery;
