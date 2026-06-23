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

import numpy as np

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.noise_suppression_service import NoiseSuppressionService
from app.services.noise_classification_service import NoiseClassificationService
from app.services.voice_clarity_service import VoiceClarityService
from app.services.audio_quality_service import AudioQualityService
from app.services import session

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

            # Convert bytes to numpy array for classification/quality
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # 3. Noise classification on raw input
            classification_obj = await asyncio.get_event_loop().run_in_executor(
                None, classifier.classify, samples
            )
            
            # Map classification result to frontend expected strings
            noise_type_map = {
                "silence": "Clean / No Noise",
                "speech": "Clean / No Noise",
                "background_noise": "Background Conversation",
                "traffic": "Traffic Noise",
                "wind": "Other",
                "keyboard": "Keyboard Typing",
                "fan": "Fan Noise",
                "music": "Other",
                "unknown": "Other",
            }
            noise_class_str = noise_type_map.get(classification_obj.noise_type.value, "Other")

            # 4. Voice clarity logic
            clarity_score = 100
            if snr_db < 10:
                clarity_score -= int((10 - snr_db) * 5)
            clarity_score = max(0, min(100, clarity_score))

            t1 = time.perf_counter()
            processing_ms = (t1 - t0) * 1000

            # 5. Audio quality composite
            # Calculate waveform bars
            bars = []
            chunk_size = len(samples) // 50
            if chunk_size > 0:
                for i in range(50):
                    chunk = samples[i*chunk_size : (i+1)*chunk_size]
                    rms = np.sqrt(np.mean(chunk**2) + 1e-12)
                    db = 20 * np.log10(rms)
                    val = max(0, min(100, (db + 60) * (100 / 60)))
                    bars.append(int(val))
            else:
                bars = [0] * 50

            # Estimate metrics
            rms_db = 20 * np.log10(np.sqrt(np.mean(samples**2) + 1e-12))
            mic_status = "connected"
            if rms_db < -55:
                mic_status = "silent"

            # Noise score (lower is better, frontend might expect 0-100 where higher is noisier)
            # Actually frontend `NoiseLevelCard` says "Noise Score", lower = quieter.
            # Let's map snr_db to noise_score. snr > 20 is score 0. snr < 0 is score 100.
            noise_score = max(0, min(100, int(100 - (snr_db * 5))))

            quality_score = max(0, min(100, int((snr_db + 20) * 2.5)))

            # --- Build live alerts ---
            live_alerts = []
            if snr_db < 0:
                live_alerts.append({
                    "message": f"Very high noise detected — SNR {snr_db:.1f} dB",
                    "time": time.strftime("%I:%M %p"),
                    "level": "critical",
                })
            elif snr_db < 5:
                live_alerts.append({
                    "message": f"Elevated noise level — SNR {snr_db:.1f} dB",
                    "time": time.strftime("%I:%M %p"),
                    "level": "warning",
                })
            if noise_class_str not in ("Clean / No Noise", "Other"):
                live_alerts.append({
                    "message": f"Detected: {noise_class_str} ({classification_obj.confidence:.0%} confidence)",
                    "time": time.strftime("%I:%M %p"),
                    "level": "info",
                })

            # --- Build response payload ---
            # Encode suppressed audio as base64 for optional client-side recording
            suppressed_b64 = base64.b64encode(suppressed_bytes).decode("ascii")

            # Get current engine info for frontend visibility
            engine_status = suppressor.get_status()

            session.update_metrics(
                noise_score=noise_score,
                voice_clarity=clarity_score,
                audio_quality=quality_score,
                noise_class=noise_class_str,
                snr_db=round(snr_db, 1),
                speech_presence=classification_obj.noise_type.value == "speech" or snr_db > 5,
                waveform_bars=bars,
            )

            payload = {
                "type": "metrics",
                "microphone_status": mic_status,
                "noise_score": noise_score,
                "voice_clarity": clarity_score,
                "latency": int(processing_ms),
                "audio_quality": quality_score,
                "noise_class": noise_class_str,
                "noise_confidence": classification_obj.confidence,
                "noise_level": round(rms_db, 1),
                "speech_presence": classification_obj.noise_type.value == "speech" or snr_db > 5,
                "snr_db": round(snr_db, 1),
                "waveform_bars": bars,
                "alerts": live_alerts,
                "suppression_enabled": suppression_enabled,
                "suppressed_audio_b64": suppressed_b64,
                "features": {},
                "engine": engine_status["engine"],
                "deepfilternet_active": engine_status["deepfilternet_active"],
            }

            await websocket.send_text(json.dumps(payload))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket Error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
