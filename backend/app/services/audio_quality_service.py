import os
import librosa
import numpy as np

class AudioQualityService:
    """
    Service to analyze audio quality metrics including
    - Voice Clarity Score (0-100)
    - Noise Level (0-100, lower is better)
    - Speech Presence Percentage
    - Overall Audio Quality Score (0-100)
    """
    
    @staticmethod
    def analyze_quality(audio_path: str) -> dict:
        """
        Analyzes audio quality metrics for an input audio file.
        
        Args:
            audio_path: Path to the audio file.
            
        Returns:
            dict: Dictionary containing:
                - voice_clarity (0-100)
                - noise_level (0-100)
                - speech_presence (0-100)
                - audio_quality (0-100)
        """
        try:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            # Load audio (downsample to 16kHz for uniform processing, mono)
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            
            if len(y) == 0:
                return {
                    "voice_clarity": 0,
                    "noise_level": 100,
                    "speech_presence": 0,
                    "audio_quality": 0
                }
            
            # 1. Compute RMS energy to detect speech activity
            # Using smaller frame_length and hop_length for better time resolution
            rms = librosa.feature.rms(y=y, frame_length=256, hop_length=128)[0]
            
            if len(rms) == 0:
                 return {
                    "voice_clarity": 0,
                    "noise_level": 100,
                    "speech_presence": 0,
                    "audio_quality": 0
                }
            
            # Sort RMS values to estimate noise floor (quietest 20% of frames)
            sorted_rms = np.sort(rms)
            n_frames = len(sorted_rms)
            noise_floor = np.mean(sorted_rms[:max(1, int(n_frames * 0.2))])
            
            if noise_floor < 1e-5:
                noise_floor = 1e-5
            
            # 2. Compute Speech Presence Percentage (SPP)
            # Threshold is set at 2.5x the noise floor (adaptive threshold)
            speech_threshold = noise_floor * 2.5
            speech_frames = np.sum(rms > speech_threshold)
            speech_presence = int((speech_frames / n_frames) * 100) if n_frames > 0 else 0
            
            # 3. Calculate Voice Clarity Score
            # Estimate signal level from the loudest 20% of frames
            signal_level = np.mean(sorted_rms[int(n_frames * 0.8):]) if n_frames > 10 else np.max(sorted_rms)
            if signal_level < 1e-5:
                signal_level = 1e-5
            
            # Calculate SNR in dB
            snr_db = 20 * np.log10(signal_level / noise_floor)
            
            # Map SNR to clarity score (0-100)
            # 0 dB SNR -> 10% (very poor)
            # 35 dB SNR -> 100% (studio quality)
            min_snr = 0.0
            max_snr = 35.0
            
            if snr_db <= min_snr:
                clarity = 10
            elif snr_db >= max_snr:
                clarity = 100
            else:
                # Linear mapping
                clarity = int(10 + (snr_db / max_snr) * 90)
            
            clarity = np.clip(clarity, 0, 100)
            
            # 4. Compute Noise Level
            # Inverse relationship with clarity, but also consider noise floor magnitude
            # High noise floor should result in higher noise level
            noise_level_from_clarity = int(100 - clarity)
            noise_level_from_floor = int(min((noise_floor / 0.01) * 100, 100))  # 0.01 is reference noise floor
            
            # Combine: prioritize floor for very high noise, clarity for moderate
            noise_level = int(noise_level_from_clarity * 0.6 + noise_level_from_floor * 0.4)
            noise_level = np.clip(noise_level, 0, 100)
            
            # 5. Aggregate Audio Quality Score
            # Quality = (Clarity * 0.6) + (Speech Presence * 0.2) + (100 - Noise Level) * 0.2
            # This gives highest weight to voice clarity
            quality = int((clarity * 0.6) + (speech_presence * 0.2) + ((100 - noise_level) * 0.2))
            quality = np.clip(quality, 0, 100)
            
            return {
                "voice_clarity": int(clarity),
                "noise_level": int(noise_level),
                "speech_presence": int(speech_presence),
                "audio_quality": int(quality)
            }
            
        except Exception as e:
            print(f"Error analyzing audio quality: {str(e)}")
            # Return neutral values on error
            return {
                "voice_clarity": 50,
                "noise_level": 50,
                "speech_presence": 50,
                "audio_quality": 50
            }
