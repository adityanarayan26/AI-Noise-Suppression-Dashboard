import datetime
from typing import Optional, List

# In-memory store for active metrics
current_metrics = {
    "microphone_status": "connected",
    "noise_score": 0,
    "voice_clarity": 100,
    "latency": 50,
    "audio_quality": 100,
    "noise_class": "Clean / No Noise",
    "snr_db": 0.0,
    "speech_presence": False,
    "waveform_bars": [0] * 50,
}

# In-memory store for active alerts
current_alerts = [
    {
        "message": "System initialized and ready.",
        "time": datetime.datetime.now().strftime("%I:%M %p")
    }
]

def update_metrics(
    noise_score: int,
    voice_clarity: int,
    audio_quality: int,
    noise_class: Optional[str] = None,
    snr_db: Optional[float] = None,
    speech_presence: Optional[bool] = None,
    waveform_bars: Optional[List[int]] = None,
):
    global current_metrics
    current_metrics["noise_score"] = noise_score
    current_metrics["voice_clarity"] = voice_clarity
    current_metrics["audio_quality"] = audio_quality
    if noise_class is not None:
        current_metrics["noise_class"] = noise_class
    if snr_db is not None:
        current_metrics["snr_db"] = snr_db
    if speech_presence is not None:
        current_metrics["speech_presence"] = speech_presence
    if waveform_bars is not None:
        current_metrics["waveform_bars"] = waveform_bars

def add_alert(message: str):
    global current_alerts
    # Insert new alert at the beginning of the list
    current_alerts.insert(0, {
        "message": message,
        "time": datetime.datetime.now().strftime("%I:%M %p")
    })
    # Keep only the 10 most recent alerts
    current_alerts = current_alerts[:10]
