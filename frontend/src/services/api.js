import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  processAudio: (wavBlob) => {
    const formData = new FormData();
    formData.append('file', wavBlob, 'recording.wav');
    return apiClient.post('/api/audio/process', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  getCloudinaryFiles: () => apiClient.get('/audio/files'),
};

export const mediaUrl = (url) => {
  if (!url) return url;
  if (/^https?:\/\//i.test(url) || url.startsWith('blob:') || url.startsWith('data:')) {
    return url;
  }
  return `${API_BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`;
};

export default apiClient;
