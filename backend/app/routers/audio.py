import os
import shutil
import uuid
import time
import base64
import io
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
        
        noisy_file_path = os.path.join(UPLOAD_DIR_NOISY, file.filename)
        with open(noisy_file_path, "wb") as buffer:
            buffer.write(file_bytes)
            
        branch = get_current_branch()
        
        cloudinary_url = CloudinaryService.upload_audio(
            file_bytes=file_bytes, 
            folder=f"{branch}/beforeNoiseSuppression", 
            filename=file.filename.split('.')[0]
        )
        
        # UI testing ke liye dummy audio ko afterNoiseSuppression mein daal rahe hain.
        # Yahan par aapko apna actual ML model ka output dalna hai.
        CloudinaryService.upload_audio(
            file_bytes=file_bytes, 
            folder=f"{branch}/afterNoiseSuppression", 
            filename=file.filename.split('.')[0] + "_clean"
        )
        
        # 2. Define path for clean audio
        clean_file_path = os.path.join(UPLOAD_DIR_CLEAN, file.filename)
        
        # 3. Apply noise suppression
        suppression_result = suppression_service.process_audio(noisy_file_path, clean_file_path)
        if not suppression_result.get("success"):
            raise HTTPException(status_code=500, detail=f"Suppression model failed: {suppression_result.get('error')}")

        # 4. Classify noise type using our dedicated classifier
        noise_type = NoiseClassificationService.classify_noise(noisy_file_path)

        # 5. Analyze audio quality metrics using our quality service
        quality_metrics = AudioQualityService.analyze_quality(noisy_file_path)

        # 6. Update global session metrics
        session.update_metrics(
            noise_score=quality_metrics["noise_level"],
            voice_clarity=quality_metrics["voice_clarity"],
            audio_quality=quality_metrics["audio_quality"]
        )

        # 7. Log a new alert for this audio upload
        session.add_alert(
            f"Processed {file.filename}: Dominant noise was '{noise_type}' (Level: {quality_metrics['noise_level']}%)."
        )

        return {
            "message": f"Successfully processed file: {file.filename}",
            "status": "success",
            "noise_type": noise_type,
            "voice_clarity": quality_metrics["voice_clarity"],
            "noise_score": quality_metrics["noise_level"],
            "speech_presence": quality_metrics["speech_presence"],
            "audio_quality": quality_metrics["audio_quality"],
            "clean_audio_url": cloudinary_url
        }

    except Exception as e:
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

        # Compute SNR before and after
        raw_audio, raw_sr = sf.read(raw_path)
        clean_audio, clean_sr = sf.read(clean_path)

        def compute_snr(audio_data):
            if len(audio_data) == 0:
                return 0.0
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)
            spectrum = np.fft.rfft(audio_data)
            magnitude = np.abs(spectrum)
            freq_bins = np.fft.rfftfreq(len(audio_data), d=1.0 / 16000)
            speech_mask = (freq_bins >= 300) & (freq_bins <= 3400)
            noise_mask = ~speech_mask
            speech_power = (
                np.mean(magnitude[speech_mask] ** 2) if speech_mask.any() else 1e-10
            )
            noise_power = (
                np.mean(magnitude[noise_mask] ** 2) if noise_mask.any() else 1e-10
            )
            snr = 10.0 * np.log10(speech_power / (noise_power + 1e-10))
            return float(np.clip(snr, -20.0, 60.0))

        snr_before = compute_snr(raw_audio)
        snr_after = compute_snr(clean_audio)

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
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process audio: {str(e)}"
        )
