import os
import uuid
import time
import base64
from pathlib import Path
import soundfile as sf
import numpy as np
import noisereduce as nr
from fastapi import APIRouter, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from typing import List
from app.models.schemas import Alert, AudioUploadResponse
from app.services import session
from app.services.noise_suppression_service import NoiseSuppressionService
from app.services.noise_classification_service import NoiseClassificationService
from app.services.audio_quality_service import AudioQualityService
from app.services.cloudinary_service import CloudinaryService
import subprocess

def get_current_branch():
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        return branch
    except Exception:
        return "main"

router = APIRouter(tags=["Audio"])

# Create directories to store noisy and clean files
UPLOAD_DIR_NOISY = "uploads/noisy"
UPLOAD_DIR_CLEAN = "uploads/clean"
os.makedirs(UPLOAD_DIR_NOISY, exist_ok=True)
os.makedirs(UPLOAD_DIR_CLEAN, exist_ok=True)

# Initialize the suppression service
suppression_service = NoiseSuppressionService()

NOISE_TYPE_MAP = {
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


def safe_upload_name(filename: str) -> str:
    stem = Path(filename or "audio").stem
    suffix = Path(filename or "audio.wav").suffix or ".wav"
    safe_stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem)
    return f"{safe_stem}_{uuid.uuid4().hex[:10]}{suffix}"


def static_audio_url(path: str) -> str:
    normalized = Path(path).as_posix()
    if normalized.startswith("uploads/"):
        normalized = normalized[len("uploads/"):]
    return f"/static/{normalized}"


def waveform_bars(audio_data: np.ndarray, count: int = 50) -> list[int]:
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)
    audio_data = audio_data.astype(np.float32)
    if len(audio_data) == 0:
        return [0] * count

    chunks = np.array_split(audio_data, count)
    bars = []
    for chunk in chunks:
        if len(chunk) == 0:
            bars.append(0)
            continue
        rms = np.sqrt(np.mean(chunk ** 2) + 1e-12)
        db = 20 * np.log10(rms)
        bars.append(int(max(0, min(100, (db + 60) * (100 / 60)))))
    return bars


def compute_band_snr(audio_data: np.ndarray, sample_rate: int) -> float:
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)
    if len(audio_data) == 0:
        return 0.0
    spectrum = np.fft.rfft(audio_data)
    magnitude = np.abs(spectrum)
    freq_bins = np.fft.rfftfreq(len(audio_data), d=1.0 / sample_rate)
    speech_mask = (freq_bins >= 300) & (freq_bins <= 3400)
    noise_mask = ~speech_mask
    speech_power = np.mean(magnitude[speech_mask] ** 2) if speech_mask.any() else 1e-10
    noise_power = np.mean(magnitude[noise_mask] ** 2) if noise_mask.any() else 1e-10
    snr = 10.0 * np.log10(speech_power / (noise_power + 1e-10))
    return float(np.clip(snr, -20.0, 60.0))

@router.get("/alerts", response_model=List[Alert])
def get_alerts():
    # Return the dynamic alerts list from session state
    return session.current_alerts

@router.post("/audio/upload", response_model=AudioUploadResponse)
def upload_audio(file: UploadFile = File(...)):
    try:
        # 1. Save uploaded file to noisy uploads folder locally and to Cloudinary
        file_bytes = file.file.read()
        file.file.seek(0)

        stored_filename = safe_upload_name(file.filename)
        noisy_file_path = os.path.join(UPLOAD_DIR_NOISY, stored_filename)
        with open(noisy_file_path, "wb") as buffer:
            buffer.write(file_bytes)

        branch = get_current_branch()

        cloudinary_url = None
        try:
            cloudinary_url = CloudinaryService.upload_audio(
                file_bytes=file_bytes,
                folder=f"{branch}/beforeNoiseSuppression",
                filename=Path(stored_filename).stem
            )
        except Exception as upload_err:
            print(f"Cloudinary original upload skipped: {upload_err}")

        # 2. Define path for clean audio
        clean_file_path = os.path.join(UPLOAD_DIR_CLEAN, stored_filename)

        # 3. Apply noise suppression
        suppression_result = suppression_service.process_audio(noisy_file_path, clean_file_path)
        if not suppression_result.get("success"):
            raise HTTPException(status_code=500, detail=f"Suppression model failed: {suppression_result.get('error')}")

        # 4. Upload the ACTUALLY SUPPRESSED audio to Cloudinary (not the raw copy)
        clean_cloudinary_url = None
        if os.path.exists(clean_file_path):
            with open(clean_file_path, "rb") as cf:
                clean_bytes = cf.read()
            try:
                clean_cloudinary_url = CloudinaryService.upload_audio(
                    file_bytes=clean_bytes,
                    folder=f"{branch}/afterNoiseSuppression",
                    filename=Path(stored_filename).stem + "_clean"
                )
            except Exception as upload_err:
                print(f"Cloudinary clean upload skipped: {upload_err}")

        # 5. Read audio into numpy for classification & quality analysis
        audio_data, sr = sf.read(noisy_file_path)
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=1)
        audio_data = audio_data.astype(np.float32)
        clean_audio_data, clean_sr = sf.read(clean_file_path)
        if clean_audio_data.ndim > 1:
            clean_audio_data = np.mean(clean_audio_data, axis=1)
        clean_audio_data = clean_audio_data.astype(np.float32)

        # 6. Classify noise type using instance method
        classifier = NoiseClassificationService(sample_rate=sr)
        classification = classifier.classify(audio_data)

        # Map enum to display-friendly string
        noise_type = NOISE_TYPE_MAP.get(classification.noise_type.value, "Other")

        # 7. Compute quality metrics inline (same logic as ws_audio)
        snr_db = classification.snr_db
        snr_after = compute_band_snr(clean_audio_data, clean_sr)

        noise_level = max(0, min(100, int(100 - (snr_db * 5))))
        voice_clarity = 100
        if snr_db < 10:
            voice_clarity -= int((10 - snr_db) * 5)
        voice_clarity = max(0, min(100, voice_clarity))
        audio_quality = max(0, min(100, int((snr_db + 20) * 2.5)))
        speech_presence = classification.noise_type.value == "speech" or snr_db > 5
        bars = waveform_bars(audio_data)
        engine_status = suppression_service.get_status()

        # 8. Update global session metrics
        session.update_metrics(
            noise_score=noise_level,
            voice_clarity=voice_clarity,
            audio_quality=audio_quality,
            noise_class=noise_type,
            snr_db=round(float(snr_db), 1),
            speech_presence=speech_presence,
            waveform_bars=bars,
        )

        # 9. Log a new alert for this audio upload
        session.add_alert(
            f"Processed {file.filename}: Detected '{noise_type}' (SNR: {snr_db:.1f} dB, Clarity: {voice_clarity}%)"
        )

        return {
            "message": f"Successfully processed file: {file.filename}",
            "status": "success",
            "noise_type": noise_type,
            "noise_confidence": classification.confidence,
            "voice_clarity": voice_clarity,
            "noise_score": noise_level,
            "speech_presence": speech_presence,
            "audio_quality": audio_quality,
            "snr_db": round(float(snr_db), 1),
            "snr_before_db": round(float(snr_db), 1),
            "snr_after_db": round(float(snr_after), 1),
            "waveform_bars": bars,
            "original_audio_url": static_audio_url(noisy_file_path),
            "clean_audio_url": clean_cloudinary_url or static_audio_url(clean_file_path),
            "cloudinary_original_url": cloudinary_url,
            "cloudinary_clean_url": clean_cloudinary_url,
            "engine": engine_status["engine"],
            "deepfilternet_active": engine_status["deepfilternet_active"],
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to process audio: {str(e)}")

@router.get("/audio/files")
def get_audio_files():
    try:
        branch = get_current_branch()
        before_files = CloudinaryService.get_audio_files(f"{branch}/beforeNoiseSuppression")
        after_files = CloudinaryService.get_audio_files(f"{branch}/afterNoiseSuppression")
        return {
            "before": before_files,
            "after": after_files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Cloudinary files: {str(e)}")

@router.websocket("/audio/stream")
async def audio_stream(websocket: WebSocket, suppress: bool = True):
    await websocket.accept()
    print(f"WebSocket connection established for real-time audio stream. Suppression: {suppress}")
    
    # Buffers to calculate live metrics (3 seconds sliding window)
    rolling_buffer = []
    full_session_buffer = [] # Accumulate all audio to save at the end
    samples_count = 0
    
    # State to rate-limit alerts and notifications
    last_alert_time = 0
    last_detected_noise = "Other"
    
    try:
        while True:
            # Receive binary chunk (PCM Float32 at 16kHz)
            data = await websocket.receive_bytes()
            if not data:
                break
            
            # Convert bytes to numpy Float32 array
            audio_chunk = np.frombuffer(data, dtype=np.float32)
            
            if len(audio_chunk) > 0:
                full_session_buffer.append(audio_chunk)
                
                if suppress:
                    # 1. Apply fast stationary noise reduction using noisereduce
                    cleaned_chunk = nr.reduce_noise(
                        y=audio_chunk,
                        sr=16000,
                        stationary=True,
                        prop_decrease=0.85
                    )
                else:
                    cleaned_chunk = audio_chunk
                
                # 2. Accumulate in the sliding buffer for stream analysis
                rolling_buffer.append(audio_chunk)
                samples_count += len(audio_chunk)
                
                # 3 seconds window at 16kHz = 48,000 samples
                if samples_count >= 48000:
                    # Concatenate all accumulated chunks
                    full_signal = np.concatenate(rolling_buffer)
                    # Keep only the last 3 seconds
                    analysis_signal = full_signal[-48000:]
                    
                    # Create temporary unique file for analysis
                    temp_filename = f"temp_stream_{uuid.uuid4().hex}.wav"
                    try:
                        sf.write(temp_filename, analysis_signal, 16000)
                        
                        # Analyze noise type and quality
                        noise_type = NoiseClassificationService.classify_noise(temp_filename)
                        quality_metrics = AudioQualityService.analyze_quality(temp_filename)
                        
                        # Update session metrics in real time
                        session.update_metrics(
                            noise_score=quality_metrics["noise_level"],
                            voice_clarity=quality_metrics["voice_clarity"],
                            audio_quality=quality_metrics["audio_quality"]
                        )
                        
                        # Log alert if specific noise detected (prevent spamming: rate-limit to once per 10s)
                        current_time = time.time()
                        if noise_type != "Other" and (noise_type != last_detected_noise or (current_time - last_alert_time) > 10):
                            session.add_alert(f"Live Mic: Detected '{noise_type}' background noise.")
                            last_alert_time = current_time
                            last_detected_noise = noise_type
                            
                    except Exception as analysis_err:
                        print(f"Error in stream analysis: {str(analysis_err)}")
                    finally:
                        if os.path.exists(temp_filename):
                            os.remove(temp_filename)
                    
                    # Reset buffer to keep sliding window context
                    rolling_buffer = [analysis_signal]
                    samples_count = len(analysis_signal)
                
                # 3. Convert back to raw bytes and send cleaned audio
                cleaned_bytes = cleaned_chunk.astype(np.float32).tobytes()
                await websocket.send_bytes(cleaned_bytes)
                
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
        # Save session to Cloudinary
        if full_session_buffer:
            session_audio = np.concatenate(full_session_buffer)
            session_filename = f"session_{uuid.uuid4().hex}.wav"
            try:
                sf.write(session_filename, session_audio, 16000)
                with open(session_filename, "rb") as f:
                    file_bytes = f.read()
                    
                branch = get_current_branch()
                folder = f"{branch}/afterNoiseSuppression" if suppress else f"{branch}/beforeNoiseSuppression"
                CloudinaryService.upload_audio(
                    file_bytes=file_bytes,
                    folder=folder,
                    filename=f"live_{'suppressed' if suppress else 'raw'}_{int(time.time())}"
                )
                print(f"Uploaded live session to {folder}")
            except Exception as e:
                print(f"Failed to save stream to Cloudinary: {e}")
            finally:
                if os.path.exists(session_filename):
                    os.remove(session_filename)

    except Exception as e:
        print(f"Error in WebSocket audio stream: {str(e)}")


@router.post("/api/audio/process")
async def process_audio_comparison(file: UploadFile = File(...)):
    """
    Accept a WAV recording, run DeepFilterNet suppression, and return
    both raw + suppressed audio as base64-encoded WAV along with SNR metrics.

    Used by the frontend's recordAndProcess() for before/after comparison.
    """
    try:
        file_bytes = await file.read()

        # Save to temp file
        temp_id = uuid.uuid4().hex
        raw_path = os.path.join(UPLOAD_DIR_NOISY, f"comparison_raw_{temp_id}.wav")
        clean_path = os.path.join(UPLOAD_DIR_CLEAN, f"comparison_clean_{temp_id}.wav")

        with open(raw_path, "wb") as f:
            f.write(file_bytes)

        # Create a fresh suppression service instance for file processing
        file_suppressor = NoiseSuppressionService()

        # Run suppression
        result = file_suppressor.process_audio(raw_path, clean_path)
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Suppression failed: {result.get('error')}",
            )

        # Compute SNR, waveform, and classification before/after
        raw_audio, raw_sr = sf.read(raw_path)
        clean_audio, clean_sr = sf.read(clean_path)
        if raw_audio.ndim > 1:
            raw_audio = np.mean(raw_audio, axis=1)
        raw_audio = raw_audio.astype(np.float32)
        if clean_audio.ndim > 1:
            clean_audio = np.mean(clean_audio, axis=1)
        clean_audio = clean_audio.astype(np.float32)

        classifier = NoiseClassificationService(sample_rate=raw_sr)
        classification = classifier.classify(raw_audio)
        noise_type = NOISE_TYPE_MAP.get(classification.noise_type.value, "Other")
        snr_before = classification.snr_db
        snr_after = compute_band_snr(clean_audio, clean_sr)
        noise_level = max(0, min(100, int(100 - (snr_before * 5))))
        voice_clarity = 100
        if snr_before < 10:
            voice_clarity -= int((10 - snr_before) * 5)
        voice_clarity = max(0, min(100, voice_clarity))
        audio_quality = max(0, min(100, int((snr_before + 20) * 2.5)))
        speech_presence = classification.noise_type.value == "speech" or snr_before > 5
        bars = waveform_bars(raw_audio)
        engine_status = file_suppressor.get_status()

        session.update_metrics(
            noise_score=noise_level,
            voice_clarity=voice_clarity,
            audio_quality=audio_quality,
            noise_class=noise_type,
            snr_db=round(float(snr_before), 1),
            speech_presence=speech_presence,
            waveform_bars=bars,
        )
        session.add_alert(
            f"Recorded 5s sample: Detected '{noise_type}' (SNR: {snr_before:.1f} dB, Clarity: {voice_clarity}%)"
        )

        # Encode both files as base64
        with open(raw_path, "rb") as f:
            raw_b64 = base64.b64encode(f.read()).decode("ascii")
        with open(clean_path, "rb") as f:
            clean_b64 = base64.b64encode(f.read()).decode("ascii")

        # Cleanup temp files
        for p in (raw_path, clean_path):
            if os.path.exists(p):
                os.remove(p)

        return {
            "raw_audio_b64": raw_b64,
            "suppressed_audio_b64": clean_b64,
            "snr_before_db": round(snr_before, 1),
            "snr_after_db": round(snr_after, 1),
            "noise_type": noise_type,
            "noise_class": noise_type,
            "noise_confidence": classification.confidence,
            "noise_score": noise_level,
            "voice_clarity": voice_clarity,
            "audio_quality": audio_quality,
            "speech_presence": speech_presence,
            "snr_db": round(float(snr_before), 1),
            "waveform_bars": bars,
            "engine": engine_status["engine"],
            "deepfilternet_active": engine_status["deepfilternet_active"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process audio: {str(e)}"
        )
