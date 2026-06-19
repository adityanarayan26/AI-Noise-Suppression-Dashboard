from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, metrics, audio
from app.routers import ws_audio

app = FastAPI(
    title="AI Interview Audio Monitoring Backend",
    description="Backend API for the audio monitoring dashboard with real-time AI noise suppression.",
    version="2.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(audio.router)
app.include_router(ws_audio.router)
