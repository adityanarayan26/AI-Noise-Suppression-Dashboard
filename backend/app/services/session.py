import datetime

# In-memory store for active metrics
current_metrics = {
    "microphone_status": "connected",
    "noise_score": 0,
    "voice_clarity": 100,
    "latency": 50,
    "audio_quality": 100
}

# In-memory store for active alerts
current_alerts = [
    {
        "message": "System initialized and ready.",
        "time": datetime.datetime.now().strftime("%I:%M %p")
    }
]

def update_metrics(noise_score: int, voice_clarity: int, audio_quality: int):
    global current_metrics
    current_metrics["noise_score"] = noise_score
    current_metrics["voice_clarity"] = voice_clarity
    current_metrics["audio_quality"] = audio_quality

def add_alert(message: str):
    global current_alerts
    # Insert new alert at the beginning of the list
    current_alerts.insert(0, {
        "message": message,
        "time": datetime.datetime.now().strftime("%I:%M %p")
    })
    # Keep only the 10 most recent alerts
    current_alerts = current_alerts[:10]
