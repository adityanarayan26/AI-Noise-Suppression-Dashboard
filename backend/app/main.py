from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, metrics, audio

app = FastAPI(
    title="AI Interview Audio Monitoring Backend",
    description="Backend API for the audio monitoring dashboard.",
    version="1.0.0",
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
