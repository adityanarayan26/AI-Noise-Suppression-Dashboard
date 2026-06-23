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
    noise_class: Optional[str] = "Other"
    snr_db: Optional[float] = 0.0
    speech_presence: Optional[bool] = False
    waveform_bars: Optional[List[int]] = None

class Alert(BaseModel):
    message: str
    time: str

class AudioUploadResponse(BaseModel):
    message: str
    status: str
    noise_type: str
    noise_confidence: float
    voice_clarity: int
    noise_score: int
    speech_presence: bool
    audio_quality: int
    snr_db: float
    snr_before_db: float
    snr_after_db: float
    waveform_bars: List[int]
    original_audio_url: str
    clean_audio_url: str
    cloudinary_original_url: Optional[str] = None
    cloudinary_clean_url: Optional[str] = None
    engine: str
    deepfilternet_active: bool
