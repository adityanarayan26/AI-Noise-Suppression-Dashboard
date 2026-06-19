import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const healthService = {
  getHealth: () => apiClient.get('/health'),
};

export const metricsService = {
  getMetrics: () => apiClient.get('/metrics'),
};

export const audioService = {
  getAlerts: () => apiClient.get('/alerts'),
  uploadAudio: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/audio/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  /**
   * Send a WAV Blob to the backend and receive both raw and AI-suppressed WAV
   * as base64 strings, plus SNR metadata.
   * @param {Blob} wavBlob
   * @returns {Promise<{raw_audio_b64, suppressed_audio_b64, duration_s, snr_before_db, snr_after_db}>}
   */
  processAudio: (wavBlob) => {
    const formData = new FormData();
    formData.append('file', wavBlob, 'recording.wav');
    return apiClient.post('/api/audio/process', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

export default apiClient;
