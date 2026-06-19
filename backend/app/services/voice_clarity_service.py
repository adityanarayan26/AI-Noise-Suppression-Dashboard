import numpy as np
from numpy.fft import rfft

class VoiceClarityService:
    """
    Measures voice clarity using two complementary techniques:

    1. Harmonic-to-Noise Ratio (HNR) via autocorrelation:
       - The autocorrelation of a voiced speech signal has a strong peak at the pitch period.
       - HNR = 10 * log10(r_max / (1 - r_max))  where r_max is the normalised autocorrelation peak.
       - A higher HNR means the signal is more periodic (clear voice) vs. noisy.

    2. Spectral Flatness Measure (SFM):
       - SFM = geometric_mean(|X(k)|) / arithmetic_mean(|X(k)|)
       - Close to 0 → tonal/voiced (good clarity), close to 1 → white noise (bad clarity).

    Final score (0–100) is a weighted blend of both metrics.
    """

    SAMPLE_RATE = 16000
    # Min and max fundamental frequency range for human voice (Hz)
    F0_MIN = 60
    F0_MAX = 450

    def score(self, pcm_bytes: bytes) -> dict:
        """
        Returns:
            {
                "clarity_score": int,       # 0–100
                "hnr_db": float,            # Harmonic-to-Noise Ratio in dB
                "sfm": float,               # Spectral Flatness Measure 0–1
                "voiced": bool,             # True if speech detected
            }
        """
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n = len(samples)

        if n < 512:
            return {"clarity_score": 0, "hnr_db": -20.0, "sfm": 1.0, "voiced": False}

        rms = float(np.sqrt(np.mean(samples ** 2)))

        # Very quiet frames → not voiced
        if rms < 0.003:
            return {"clarity_score": 0, "hnr_db": -20.0, "sfm": 1.0, "voiced": False}

        hnr_db = self._compute_hnr(samples)
        sfm = self._compute_sfm(samples)
        voiced = hnr_db > 0

        # Convert HNR (typically -20 to +30 dB for speech) to 0–100
        hnr_score = np.clip((hnr_db + 20) / 50 * 100, 0, 100)

        # Convert SFM (0=tonal, 1=noisy) → 0–100 score (invert)
        sfm_score = np.clip((1.0 - sfm) * 100, 0, 100)

        # Blend: HNR carries 65%, SFM carries 35%
        clarity = float(0.65 * hnr_score + 0.35 * sfm_score)
        clarity_score = int(np.clip(clarity, 0, 100))

        return {
            "clarity_score": clarity_score,
            "hnr_db": round(hnr_db, 2),
            "sfm": round(sfm, 4),
            "voiced": voiced,
        }

    def _compute_hnr(self, samples: np.ndarray) -> float:
        """
        Estimate HNR using normalised autocorrelation.
        Looks for peak in the lag range corresponding to F0_MIN–F0_MAX Hz.
        """
        # Subtract mean (centre the signal)
        x = samples - np.mean(samples)

        # Full autocorrelation via FFT for efficiency
        n = len(x)
        fft_size = 2 ** int(np.ceil(np.log2(2 * n - 1)))
        X = np.fft.rfft(x, n=fft_size)
        acf_full = np.fft.irfft(X * np.conj(X))
        acf = acf_full[:n]  # Keep positive lags only

        # Normalise by lag-0 (total energy)
        if acf[0] < 1e-10:
            return -20.0
        acf_norm = acf / acf[0]

        # Search in the pitch period range
        lag_min = int(self.SAMPLE_RATE / self.F0_MAX)
        lag_max = int(self.SAMPLE_RATE / self.F0_MIN)
        lag_max = min(lag_max, n - 1)

        if lag_min >= lag_max:
            return -20.0

        peak_val = float(np.max(acf_norm[lag_min:lag_max]))
        peak_val = np.clip(peak_val, 0.0001, 0.9999)

        # HNR formula
        hnr_db = 10.0 * np.log10(peak_val / (1.0 - peak_val))
        return float(np.clip(hnr_db, -20.0, 40.0))

    @staticmethod
    def _compute_sfm(samples: np.ndarray) -> float:
        """
        Spectral Flatness Measure.
        0 = perfectly tonal (voiced), 1 = perfectly flat (white noise).
        """
        spectrum = np.abs(rfft(samples)) + 1e-10
        geometric_mean = np.exp(np.mean(np.log(spectrum)))
        arithmetic_mean = np.mean(spectrum)
        sfm = geometric_mean / (arithmetic_mean + 1e-10)
        return float(np.clip(sfm, 0.0, 1.0))
