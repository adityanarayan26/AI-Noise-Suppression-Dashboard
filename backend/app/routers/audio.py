import asyncio
import base64
import io
import struct
import wave

from fastapi import APIRouter, File, UploadFile
from typing import List

from app.models.schemas import Alert, AudioUploadResponse, AudioProcessResponse
from app.services.noise_suppression_service import NoiseSuppressionService

router = APIRouter(tags=["Audio"])

# Frame size must match what the frontend sends over WebSocket (1024 samples @ 16 kHz ≈ 64 ms)
FRAME_SAMPLES = 1024
SAMPLE_RATE = 16000


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a WAV blob from raw Int16 PCM bytes
# ─────────────────────────────────────────────────────────────────────────────
def _build_wav(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # Int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: read raw PCM bytes from a WAV upload (strips WAV header)
# ─────────────────────────────────────────────────────────────────────────────
def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.readframes(wf.getnframes())


@router.get("/alerts", response_model=List[Alert])
def get_alerts():
    return [
        {"message": "Background Noise Detected", "time": "10:30 AM"},
        {"message": "Keyboard Noise Detected",   "time": "10:32 AM"},
        {"message": "High Latency Detected",      "time": "10:35 AM"},
        {"message": "Microphone Quality Reduced", "time": "10:40 AM"},
    ]


@router.post("/audio/upload", response_model=AudioUploadResponse)
def upload_audio(file: UploadFile = File(...)):
    # Legacy endpoint — kept for backward compatibility.
    return {
        "message": f"Received file {file.filename} successfully. Audio processing is skipped.",
        "status": "success",
    }


@router.post("/api/audio/process", response_model=AudioProcessResponse)
async def process_audio(file: UploadFile = File(...)):
    """
    Single-recording before/after comparison endpoint.

    Accepts a WAV file of raw microphone audio, runs it through the AI
    noise-suppression pipeline frame-by-frame, and returns both the
    original and suppressed audio as base64-encoded WAV blobs.

    The frontend can then present both side-by-side for A/B listening.
    """
    wav_bytes = await file.read()

    # Strip WAV header → raw Int16 PCM bytes
    raw_pcm = _wav_to_pcm(wav_bytes)

    # Per-request suppressor (fresh noise profile for every recording)
    suppressor = NoiseSuppressionService()
    suppressor.set_suppression(True)

    suppressed_frames: list[bytes] = []
    total_bytes = len(raw_pcm)
    frame_bytes = FRAME_SAMPLES * 2  # 2 bytes per Int16 sample

    # Process frame-by-frame (same chunk size as the live WS pipeline)
    offset = 0
    while offset + frame_bytes <= total_bytes:
        frame = raw_pcm[offset: offset + frame_bytes]
        suppressed_frame = await asyncio.get_event_loop().run_in_executor(
            None, suppressor.process, frame
        )
        suppressed_frames.append(suppressed_frame)
        offset += frame_bytes

    # Handle any remaining samples (partial last frame — pad with silence)
    if offset < total_bytes:
        remainder = raw_pcm[offset:]
        padding = bytes(frame_bytes - len(remainder))
        suppressed_frame = await asyncio.get_event_loop().run_in_executor(
            None, suppressor.process, remainder + padding
        )
        # Only keep the real samples, not the silence padding
        suppressed_frames.append(suppressed_frame[: len(remainder)])

    suppressed_pcm = b"".join(suppressed_frames)

    # Compute SNR before and after for the response metadata
    snr_before = suppressor.compute_snr_db(raw_pcm[:frame_bytes]) if len(raw_pcm) >= frame_bytes else 0.0
    snr_after  = suppressor.compute_snr_db(suppressed_pcm[:frame_bytes]) if len(suppressed_pcm) >= frame_bytes else 0.0

    duration_s = total_bytes / (SAMPLE_RATE * 2)

    # Build WAV blobs and base64-encode
    raw_wav        = _build_wav(raw_pcm)
    suppressed_wav = _build_wav(suppressed_pcm)

    return AudioProcessResponse(
        raw_audio_b64=base64.b64encode(raw_wav).decode("ascii"),
        suppressed_audio_b64=base64.b64encode(suppressed_wav).decode("ascii"),
        duration_s=round(duration_s, 2),
        snr_before_db=round(snr_before, 1),
        snr_after_db=round(snr_after, 1),
    )
