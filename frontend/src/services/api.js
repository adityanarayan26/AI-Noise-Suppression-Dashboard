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
};

export default apiClient;
