from pydantic import BaseModel
from typing import List

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

class AudioUploadResponse(BaseModel):
    message: str
    status: str
