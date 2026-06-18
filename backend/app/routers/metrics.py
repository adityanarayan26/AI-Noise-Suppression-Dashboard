from fastapi import APIRouter
from app.models.schemas import MetricsResponse

router = APIRouter(tags=["Metrics"])

@router.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    return {
        "microphone_status": "connected",
        "noise_score": 24,
        "voice_clarity": 89,
        "latency": 120,
        "audio_quality": 92
    }
