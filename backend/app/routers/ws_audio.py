"""
WebSocket endpoint for real-time audio processing.

Protocol:
  Client → Server (binary):  Raw Int16 PCM bytes for one audio frame (~4096 samples @ 16 kHz)
                              Prefixed with a single control byte:
                                0x00 = audio data (suppression OFF — record raw)
                                0x01 = audio data (suppression ON — apply AI pipeline)
                                0x02 = control: reset noise profile

  Server → Client (text JSON): RealtimeMetrics payload (see schemas.py)
  Server → Client (binary):    Suppressed audio frame bytes (when suppression ON)

Session lifecycle:
  - Each WebSocket connection gets its own isolated service instances.
  - The first NOISE_PROFILE_FRAMES frames are used to calibrate the noise floor.
  - Client can reset calibration by sending control byte 0x02.
"""

import asyncio
import base64
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.noise_suppression_service import NoiseSuppressionService
from app.services.noise_classification_service import NoiseClassificationService
from app.services.voice_clarity_service import VoiceClarityService
from app.services.audio_quality_service import AudioQualityService

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    """
    Real-time audio processing WebSocket.

    Each connected client gets its own set of service instances so that multiple
    simultaneous clients (e.g., multiple browser tabs) don't share state.
    """
    await websocket.accept()

    # Per-connection service instances
    suppressor = NoiseSuppressionService()
    classifier = NoiseClassificationService()
    clarity_svc = VoiceClarityService()
    quality_svc = AudioQualityService()

    suppression_enabled = False

    try:
        while True:
            raw = await websocket.receive_bytes()

            if len(raw) < 2:
                continue

            # First byte is control flag
            control = raw[0]
            pcm_bytes = raw[1:]

            # --- Handle control messages ---
            if control == 0x02:
                suppressor.reset_noise_profile()
                await websocket.send_text(json.dumps({"type": "control", "event": "profile_reset"}))
                continue

            suppression_enabled = (control == 0x01)
            suppressor.set_suppression(suppression_enabled)

            # --- Run AI pipeline ---
            t0 = time.perf_counter()

            # 1. Noise suppression (returns processed audio bytes)
            suppressed_bytes = await asyncio.get_event_loop().run_in_executor(
                None, suppressor.process, pcm_bytes
            )

            # 2. Compute SNR on the RAW input (before suppression)
            snr_db = await asyncio.get_event_loop().run_in_executor(
                None, suppressor.compute_snr_db, pcm_bytes
            )

            # 3. Noise classification on raw input
            classification = await asyncio.get_event_loop().run_in_executor(
                None, classifier.classify, pcm_bytes
            )

            # 4. Voice clarity on suppressed output (reflects improvement)
            clarity_result = await asyncio.get_event_loop().run_in_executor(
                None, clarity_svc.score, suppressed_bytes if suppression_enabled else pcm_bytes
            )

            t1 = time.perf_counter()
            processing_ms = (t1 - t0) * 1000

            # 5. Audio quality composite
            quality = await asyncio.get_event_loop().run_in_executor(
                None,
                quality_svc.analyze,
                pcm_bytes,
                snr_db,
                clarity_result["clarity_score"],
                classification["category"],
                processing_ms,
            )

            # --- Build response payload ---
            # Encode suppressed audio as base64 for optional client-side recording
            suppressed_b64 = base64.b64encode(suppressed_bytes).decode("ascii")

            payload = {
                "type": "metrics",
                "microphone_status": quality["microphone_status"],
                "noise_score": quality["noise_score"],
                "voice_clarity": quality["voice_clarity"],
                "latency": quality["latency"],
                "audio_quality": quality["audio_quality"],
                "noise_class": classification["category"],
                "noise_confidence": classification["confidence"],
                "noise_level": quality["noise_level"],
                "speech_presence": quality["speech_presence"],
                "snr_db": quality["snr_db"],
                "waveform_bars": quality["waveform_bars"],
                "alerts": quality["alerts"],
                "suppression_enabled": suppression_enabled,
                "suppressed_audio_b64": suppressed_b64,
                "features": classification.get("features", {}),
            }

            await websocket.send_text(json.dumps(payload))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
