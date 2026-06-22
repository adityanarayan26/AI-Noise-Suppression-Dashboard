"""
NoiseClassificationService
--------------------------
Classifies audio noise type using spectral + energy features.
Supports: background_noise, traffic, wind, keyboard, fan, music, speech, silence.
"""

import numpy as np
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class NoiseType(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"
    BACKGROUND_NOISE = "background_noise"
    TRAFFIC = "traffic"
    WIND = "wind"
    KEYBOARD = "keyboard"
    FAN = "fan"
    MUSIC = "music"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    noise_type: NoiseType
    confidence: float          # 0.0 – 1.0
    snr_db: float              # estimated signal-to-noise ratio
    rms_db: float              # RMS energy in dB
    dominant_freq_hz: float    # dominant frequency bin


class NoiseClassificationService:
    """
    Classifies the dominant noise type in an audio chunk using
    lightweight spectral + temporal features (no heavy ML dependency).
    """

    SAMPLE_RATE: int = 48_000          # DeepFilterNet native SR
    FRAME_SIZE: int = 1024
    HOP_SIZE: int = 512

    # Frequency band boundaries (Hz)
    _BAND_LOW   = (20,   250)
    _BAND_MID   = (250, 2_000)
    _BAND_HIGH  = (2_000, 8_000)
    _BAND_AIR   = (8_000, 20_000)

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, audio: np.ndarray) -> ClassificationResult:
        """
        Classify the noise type in *audio* (mono float32, shape [N]).

        Args:
            audio: 1-D numpy float32 array in [-1, 1].

        Returns:
            ClassificationResult with noise_type, confidence, and diagnostics.
        """
        if audio.ndim > 1:
            audio = audio.mean(axis=0)          # stereo → mono
        audio = audio.astype(np.float32)

        rms = self._rms(audio)
        rms_db = 20 * np.log10(rms + 1e-9)

        if rms_db < -60:
            return ClassificationResult(
                noise_type=NoiseType.SILENCE,
                confidence=0.95,
                snr_db=0.0,
                rms_db=rms_db,
                dominant_freq_hz=0.0,
            )

        spectrum, freqs = self._magnitude_spectrum(audio)
        dom_freq = self._dominant_frequency(spectrum, freqs)
        snr_db   = self._estimate_snr(audio)

        low_e, mid_e, high_e, air_e = self._band_energies(spectrum, freqs)
        zcr   = self._zero_crossing_rate(audio)
        sf    = self._spectral_flatness(spectrum)

        noise_type, confidence = self._classify_features(
            rms_db, dom_freq, low_e, mid_e, high_e, air_e, zcr, sf, snr_db
        )

        return ClassificationResult(
            noise_type=noise_type,
            confidence=confidence,
            snr_db=snr_db,
            rms_db=rms_db,
            dominant_freq_hz=dom_freq,
        )

    def classify_batch(self, chunks: list[np.ndarray]) -> list[ClassificationResult]:
        """Classify a list of audio chunks."""
        return [self.classify(c) for c in chunks]

    # ------------------------------------------------------------------
    # Feature extraction helpers
    # ------------------------------------------------------------------

    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(audio ** 2)))

    def _magnitude_spectrum(self, audio: np.ndarray):
        N = min(len(audio), 8192)
        windowed = audio[:N] * np.hanning(N)
        fft = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(N, d=1.0 / self.sample_rate)
        return fft, freqs

    def _dominant_frequency(self, spectrum: np.ndarray, freqs: np.ndarray) -> float:
        idx = np.argmax(spectrum)
        return float(freqs[idx])

    def _band_energy(self, spectrum, freqs, low, high) -> float:
        mask = (freqs >= low) & (freqs < high)
        if not mask.any():
            return 0.0
        return float(np.sum(spectrum[mask] ** 2))

    def _band_energies(self, spectrum, freqs):
        total = np.sum(spectrum ** 2) + 1e-9
        low  = self._band_energy(spectrum, freqs, *self._BAND_LOW)  / total
        mid  = self._band_energy(spectrum, freqs, *self._BAND_MID)  / total
        high = self._band_energy(spectrum, freqs, *self._BAND_HIGH) / total
        air  = self._band_energy(spectrum, freqs, *self._BAND_AIR)  / total
        return low, mid, high, air

    def _zero_crossing_rate(self, audio: np.ndarray) -> float:
        signs = np.sign(audio)
        signs[signs == 0] = 1
        crossings = np.sum(np.diff(signs) != 0)
        return float(crossings / len(audio))

    def _spectral_flatness(self, spectrum: np.ndarray) -> float:
        """Wiener entropy – 1 = white noise, 0 = tonal."""
        eps = 1e-9
        geom_mean = np.exp(np.mean(np.log(spectrum + eps)))
        arith_mean = np.mean(spectrum) + eps
        return float(geom_mean / arith_mean)

    def _estimate_snr(self, audio: np.ndarray, percentile: float = 10) -> float:
        """
        Rough SNR estimate: compare loud frames vs quiet frames (min-statistics).
        """
        frame_rms = [
            self._rms(audio[i : i + self.FRAME_SIZE])
            for i in range(0, len(audio) - self.FRAME_SIZE, self.HOP_SIZE)
        ]
        if not frame_rms:
            return 0.0
        noise_floor = np.percentile(frame_rms, percentile) + 1e-9
        signal_peak = np.percentile(frame_rms, 90) + 1e-9
        snr = 20 * np.log10(signal_peak / noise_floor)
        return float(np.clip(snr, -20, 60))

    # ------------------------------------------------------------------
    # Classification logic
    # ------------------------------------------------------------------

    def _classify_features(
        self,
        rms_db, dom_freq,
        low_e, mid_e, high_e, air_e,
        zcr, sf, snr_db
    ) -> tuple[NoiseType, float]:

        # Speech: mid-band dominant, moderate ZCR, mid SNR
        if mid_e > 0.40 and 80 < dom_freq < 4000 and 0.02 < zcr < 0.20:
            conf = min(0.55 + mid_e * 0.5 + (snr_db / 60) * 0.2, 0.95)
            return NoiseType.SPEECH, round(conf, 2)

        # Music: broad spectrum, tonal (low flatness), strong mid+high
        if sf < 0.15 and (mid_e + high_e) > 0.45 and snr_db > 10:
            return NoiseType.MUSIC, round(min(0.60 + (0.15 - sf) * 2, 0.90), 2)

        # Traffic: low-freq dominant, moderate flatness
        if low_e > 0.50 and dom_freq < 400:
            return NoiseType.TRAFFIC, round(min(0.55 + low_e * 0.4, 0.90), 2)

        # Wind: very flat (white-ish), high air-band energy, high ZCR
        if sf > 0.50 and air_e > 0.20 and zcr > 0.15:
            return NoiseType.WIND, round(min(0.50 + sf * 0.4, 0.88), 2)

        # Fan / HVAC: flat spectrum, low-mid dominant, continuous
        if sf > 0.30 and low_e + mid_e > 0.60 and rms_db > -45:
            return NoiseType.FAN, round(min(0.50 + sf * 0.3, 0.85), 2)

        # Keyboard: impulsive (high ZCR), high-freq content, spiky
        if zcr > 0.20 and high_e > 0.25:
            return NoiseType.KEYBOARD, round(min(0.50 + zcr * 0.8, 0.85), 2)

        # Generic background noise
        if rms_db > -55:
            return NoiseType.BACKGROUND_NOISE, 0.60

        return NoiseType.UNKNOWN, 0.40
