from fastapi import APIRouter, File, UploadFile
from typing import List
from app.models.schemas import Alert, AudioUploadResponse

router = APIRouter(tags=["Audio"])

@router.get("/alerts", response_model=List[Alert])
def get_alerts():
    return [
        {
            "message": "Background Noise Detected",
            "time": "10:30 AM"
        },
        {
            "message": "Keyboard Noise Detected",
            "time": "10:32 AM"
        },
        {
            "message": "High Latency Detected",
            "time": "10:35 AM"
        },
        {
            "message": "Microphone Quality Reduced",
            "time": "10:40 AM"
        }
    ]

@router.post("/audio/upload", response_model=AudioUploadResponse)
def upload_audio(file: UploadFile = File(...)):
    # Mock response. No audio processing required.
    return {
        "message": f"Received file {file.filename} successfully. Audio processing is skipped.",
        "status": "success"
    }
