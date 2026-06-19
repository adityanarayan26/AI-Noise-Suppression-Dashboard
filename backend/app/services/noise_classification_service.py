import os
import numpy as np
import librosa

class NoiseClassificationService:
    """
    Service to classify the dominant type of background noise in an audio file 
    using spectral features (spectral centroid, zero-crossing rate, spectral flatness).
    """

    @staticmethod
    def classify_noise(audio_path: str) -> str:
        """
        Classifies the type of background noise present in the audio file.
        
        Expected Categories:
        - Fan Noise
        - Traffic Noise
        - Keyboard Typing
        - Background Conversation
        - AC Noise
        - Other (or Clean)
        
        Args:
            audio_path: Path to the audio file.
            
        Returns:
            str: Classified noise category.
        """
        try:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")

            # Load audio (downsample to 16kHz, mono)
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            
            if len(y) == 0:
                return "Other"

            # 1. Compute spectral centroid (indicates where the center of mass of the spectrum is)
            centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            mean_centroid = np.mean(centroids)

            # 2. Compute zero-crossing rate (measures frequency of signal sign changes, high for clicks/typing)
            zcr = librosa.feature.zero_crossing_rate(y=y)[0]
            mean_zcr = np.mean(zcr)
            max_zcr = np.max(zcr)

            # 3. Compute spectral flatness (high values mean noise-like, low values mean harmonic/speech-like)
            flatness = librosa.feature.spectral_flatness(y=y)[0]
            mean_flatness = np.mean(flatness)

            # 4. Check low frequency energy ratio (traffic noise is primarily low frequency)
            # Compute Short-Time Fourier Transform
            stft = np.abs(librosa.stft(y))
            # Sum up frequencies below ~200Hz
            low_freq_bins = int(stft.shape[0] * (200 / (sr / 2)))
            low_freq_energy = np.sum(stft[:low_freq_bins, :])
            total_energy = np.sum(stft) + 1e-9
            low_freq_ratio = low_freq_energy / total_energy

            # Classify based on spectral features
            # A. Keyboard Typing: High transients, high peak zero-crossing rate relative to mean
            if max_zcr > 0.25 and mean_zcr > 0.08:
                return "Keyboard Typing"

            # B. Traffic Noise: Strong low-frequency component (engine rumbles) and low centroid
            elif low_freq_ratio > 0.45 and mean_centroid < 1000:
                return "Traffic Noise"

            # C. Fan Noise: Continuous, hiss-like (high spectral centroid and high flatness)
            elif mean_centroid > 2200 and mean_flatness > 0.008:
                return "Fan Noise"

            # D. AC Noise: Steady hum (lower centroid than fan noise but still steady and flat)
            elif 1000 <= mean_centroid <= 2200 and mean_flatness > 0.005:
                return "AC Noise"

            # E. Background Conversation: High harmonicity (very low flatness, centroid centered around human voice range)
            elif mean_flatness < 0.002 and 800 <= mean_centroid <= 2000:
                return "Background Conversation"

            else:
                return "Other"

        except Exception as e:
            print(f"Error classifying noise: {str(e)}")
            return "Other"
