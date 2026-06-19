import numpy as np
from numpy.fft import rfft

class NoiseClassificationService:
    """
    Classifies the dominant noise type in an audio frame using acoustic features.

    Features extracted per frame:
    - Zero Crossing Rate (ZCR): how often the signal crosses zero → relates to frequency character
    - Spectral Centroid: weighted mean of frequency magnitudes → brightness of sound
    - RMS Energy: root mean square of samples → overall loudness
    - Spectral Rolloff: frequency below which 85% of energy lies

    Rule-based classifier mapping feature regions to noise categories.
    These rules are derived from published acoustic properties of each noise type.
    """

    SAMPLE_RATE = 16000
    CATEGORIES = [
        "Fan Noise",
        "Traffic Noise",
        "Keyboard Typing",
        "Background Conversation",
        "AC Noise",
        "Other",
        "Clean / No Noise",
    ]

    def classify(self, pcm_bytes: bytes) -> dict:
        """
        Returns:
            {
                "category": str,
                "confidence": float,   # 0.0 – 1.0
                "features": { ... }    # for dashboard display
            }
        """
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n = len(samples)

        if n == 0:
            return {"category": "Other", "confidence": 0.5, "features": {}}

        # --- Feature extraction ---
        rms = float(np.sqrt(np.mean(samples ** 2)))

        # Zero Crossing Rate
        zcr = float(np.sum(np.diff(np.sign(samples)) != 0) / n)

        # Frequency domain
        spectrum = np.abs(rfft(samples))
        freq_bins = np.fft.rfftfreq(n, d=1.0 / self.SAMPLE_RATE)
        total_power = np.sum(spectrum ** 2) + 1e-10

        # Spectral centroid (Hz)
        centroid = float(np.sum(freq_bins * spectrum) / (np.sum(spectrum) + 1e-10))

        # Spectral rolloff (85th percentile energy frequency)
        cumulative = np.cumsum(spectrum ** 2)
        rolloff_thresh = 0.85 * total_power
        rolloff_idx = np.searchsorted(cumulative, rolloff_thresh)
        rolloff = float(freq_bins[rolloff_idx]) if rolloff_idx < len(freq_bins) else float(freq_bins[-1])

        # Low-frequency energy ratio (< 300 Hz) — fans/AC dominant here
        low_mask = freq_bins < 300
        low_energy_ratio = float(np.sum(spectrum[low_mask] ** 2) / total_power) if low_mask.any() else 0.0

        # Mid-frequency energy ratio (300–3400 Hz) — speech / keyboard
        mid_mask = (freq_bins >= 300) & (freq_bins <= 3400)
        mid_energy_ratio = float(np.sum(spectrum[mid_mask] ** 2) / total_power) if mid_mask.any() else 0.0

        features = {
            "rms": round(rms, 4),
            "zcr": round(zcr, 4),
            "centroid_hz": round(centroid, 1),
            "rolloff_hz": round(rolloff, 1),
            "low_energy_ratio": round(low_energy_ratio, 3),
            "mid_energy_ratio": round(mid_energy_ratio, 3),
        }

        # --- Rule-based classification ---
        category, confidence = self._classify_rules(rms, zcr, centroid, rolloff, low_energy_ratio, mid_energy_ratio)

        return {
            "category": category,
            "confidence": round(confidence, 2),
            "features": features,
        }

    @staticmethod
    def _classify_rules(rms, zcr, centroid, rolloff, low_ratio, mid_ratio):
        """
        Acoustic heuristics based on published literature on environmental sound classification.
        """
        # Very quiet — likely clean or silent
        if rms < 0.005:
            return "Clean / No Noise", 0.92

        # Fan / AC noise: low centroid, low ZCR, dominated by low frequencies, steady
        if centroid < 600 and low_ratio > 0.55 and zcr < 0.08:
            if low_ratio > 0.70:
                return "Fan Noise", 0.88
            else:
                return "AC Noise", 0.82

        # AC noise: similar but slightly higher centroid
        if centroid < 900 and low_ratio > 0.45 and zcr < 0.10:
            return "AC Noise", 0.78

        # Keyboard typing: very high ZCR (transient clicks), mid-high centroid
        if zcr > 0.25 and centroid > 2000 and rms < 0.15:
            return "Keyboard Typing", 0.84

        # Traffic noise: broad spectrum, moderate ZCR, mid centroid
        if centroid > 800 and centroid < 2500 and low_ratio > 0.30 and zcr > 0.08:
            return "Traffic Noise", 0.76

        # Background conversation: significant mid-band energy, speech-like ZCR
        if mid_ratio > 0.50 and zcr > 0.12 and zcr < 0.35 and centroid > 600:
            return "Background Conversation", 0.80

        # Default
        return "Other", 0.60
