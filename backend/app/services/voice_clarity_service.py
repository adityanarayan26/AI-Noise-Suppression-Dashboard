import os
import librosa
import numpy as np

class VoiceClarityService:
    """
    Service to evaluate voice clarity by estimating the signal-to-noise ratio (SNR)
    of the speech segments compared to background noise.
    """

    @staticmethod
    def calculate_clarity(audio_path: str) -> int:
        """
        Calculates a voice clarity score (0 to 100) based on estimated Signal-to-Noise Ratio (SNR).
        
        Args:
            audio_path: Path to the audio file to analyze.
            
        Returns:
            int: Clarity score from 0 (very noisy) to 100 (extremely clear).
        """
        try:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")

            # Load audio (downsample to 16kHz for uniform processing, mono)
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            
            if len(y) == 0:
                return 0

            # Calculate Root Mean Square (RMS) energy for small frames
            rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
            
            if len(rms) == 0:
                return 0

            # Sort the frame energies to estimate signal vs noise floor
            sorted_rms = np.sort(rms)
            n_frames = len(sorted_rms)

            # Estimate noise from the quietest 20% of frames
            # Estimate speech signal from the loudest 20% of frames
            if n_frames > 10:
                noise_floor = np.mean(sorted_rms[:int(n_frames * 0.2)])
                signal_level = np.mean(sorted_rms[int(n_frames * 0.8):])
            else:
                noise_floor = np.min(sorted_rms)
                signal_level = np.max(sorted_rms)

            # Avoid division by zero or log of zero
            if noise_floor < 1e-5:
                noise_floor = 1e-5
            if signal_level < 1e-5:
                signal_level = 1e-5

            # Calculate SNR in Decibels (dB)
            snr_db = 20 * np.log10(signal_level / noise_floor)
            
            # Map SNR (dB) to a 0-100 clarity score
            # 0 dB SNR -> 10% clarity (extremely poor, noise equal to speech)
            # 35 dB SNR -> 100% clarity (studio quality)
            min_snr = 0.0
            max_snr = 35.0
            
            if snr_db <= min_snr:
                score = 10
            elif snr_db >= max_snr:
                score = 100
            else:
                # Linear mapping between min_snr and max_snr
                score = int(10 + (snr_db / max_snr) * 90)

            return int(np.clip(score, 0, 100))

        except Exception as e:
            print(f"Error in calculating voice clarity: {str(e)}")
            return 50  # Fallback neutral score
