from pydantic import BaseModel
from typing import List, Optional

class HealthResponse(BaseModel):
    status: str

class MetricsResponse(BaseModel):
    microphone_status: str
    noise_score: int
    voice_clarity: int
    latency: int
    audio_quality: int

class Alert(BaseModel):
    message: str
    time: str
    level: Optional[str] = "info"

class AudioUploadResponse(BaseModel):
    message: str
    status: str

class AudioProcessResponse(BaseModel):
    """Response from POST /api/audio/process — both raw and suppressed audio as base64 WAV."""
    raw_audio_b64: str          # base64-encoded WAV of the original recording
    suppressed_audio_b64: str   # base64-encoded WAV after AI noise suppression
    duration_s: float           # recording duration in seconds
    snr_before_db: float        # SNR of the raw audio
    snr_after_db: float         # SNR of the suppressed audio

class RealtimeMetrics(BaseModel):
    """
    WebSocket message payload sent from backend to frontend for each processed audio frame.
    Contains all metrics needed to drive the dashboard in real time.
    """
    type: str = "metrics"                   # message type identifier
    microphone_status: str                  # "connected" | "silent"
    noise_score: int                        # 0–100 (higher = noisier)
    voice_clarity: int                      # 0–100 (higher = clearer)
    latency: int                            # processing latency in ms
    audio_quality: int                      # 0–100 composite quality
    noise_class: str                        # e.g. "Fan Noise", "Traffic Noise"
    noise_confidence: float                 # 0.0–1.0
    noise_level: float                      # 0.0–100.0
    speech_presence: bool                   # whether speech detected
    snr_db: float                           # raw SNR in dB
    waveform_bars: List[float]              # 50 bar heights 0–100 for visualisation
    alerts: List[Alert]                     # dynamic alerts for this frame
    suppression_enabled: bool               # current suppression toggle state
    suppressed_audio_b64: Optional[str] = None  # base64 Int16 PCM if client wants playback
