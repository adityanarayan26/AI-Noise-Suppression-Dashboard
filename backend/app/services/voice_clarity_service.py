"""
VoiceClarityService
-------------------
Post-processes DeepFilterNet output to maximise speech intelligibility.

Pipeline:
  1. Band-pass filter   – retain voice frequencies (80 Hz – 8 kHz)
  2. Spectral tilt      – de-emphasis / pre-emphasis to balance spectrum
  3. Dynamic range compression – make quiet speech louder without clipping
  4. Gentle de-reverb   – smooth residual reverberation artefacts
  5. Normalisation      – target loudness (LUFS-like peak normalisation)
"""

import numpy as np
from scipy import signal
from typing import Optional


class VoiceClaritySettings:
    """Tunable knobs for the clarity pipeline."""

    def __init__(
        self,
        bandpass_low_hz: float   = 80.0,
        bandpass_high_hz: float  = 8_000.0,
        preemphasis_coef: float  = 0.97,
        compression_threshold_db: float = -20.0,
        compression_ratio: float = 3.0,
        compression_attack_ms: float  = 5.0,
        compression_release_ms: float = 100.0,
        target_peak_db: float    = -3.0,
        apply_bandpass: bool     = True,
        apply_preemphasis: bool  = True,
        apply_compression: bool  = True,
        apply_dereveb: bool      = False, #True,
        apply_normalisation: bool= True,
    ):
        self.bandpass_low_hz      = bandpass_low_hz
        self.bandpass_high_hz     = bandpass_high_hz
        self.preemphasis_coef     = preemphasis_coef
        self.compression_threshold_db = compression_threshold_db
        self.compression_ratio    = compression_ratio
        self.compression_attack_ms  = compression_attack_ms
        self.compression_release_ms = compression_release_ms
        self.target_peak_db       = target_peak_db
        self.apply_bandpass       = apply_bandpass
        self.apply_preemphasis    = apply_preemphasis
        self.apply_compression    = apply_compression
        self.apply_dereveb        = apply_dereveb
        self.apply_normalisation  = apply_normalisation


class VoiceClarityService:
    """
    Applies a lightweight DSP post-processing chain to improve
    the perceptual clarity of speech after noise suppression.

    Works on numpy float32 arrays at any sample rate.
    """

    def __init__(
        self,
        sample_rate: int = 48_000,
        settings: Optional[VoiceClaritySettings] = None,
    ):
        self.sample_rate = sample_rate
        self.cfg = settings or VoiceClaritySettings()
        self._build_filters()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enhance(self, audio: np.ndarray) -> np.ndarray:
        """
        Run the full clarity pipeline on *audio*.

        Args:
            audio: float32 mono or stereo [samples] or [channels, samples].

        Returns:
            Processed float32 array, same shape.
        """
        stereo = audio.ndim == 2
        if stereo:
            return np.stack(
                [self._process_mono(audio[ch]) for ch in range(audio.shape[0])],
                axis=0,
            )
        return self._process_mono(audio)

    def update_settings(self, **kwargs) -> None:
        """Update settings on the fly and rebuild filters."""
        for k, v in kwargs.items():
            if hasattr(self.cfg, k):
                setattr(self.cfg, k, v)
        self._build_filters()

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _process_mono(self, audio: np.ndarray) -> np.ndarray:
        x = audio.copy().astype(np.float32)

        if self.cfg.apply_bandpass:
            x = self._bandpass(x)

        if self.cfg.apply_preemphasis:
            x = self._preemphasis(x)

        if self.cfg.apply_compression:
            x = self._compress(x)

        if self.cfg.apply_dereveb:
            x = self._dereverberate(x)

        if self.cfg.apply_normalisation:
            x = self._normalise(x)

        return np.clip(x, -1.0, 1.0)

    # ------------------------------------------------------------------
    # DSP stages
    # ------------------------------------------------------------------

    def _build_filters(self) -> None:
        nyq = self.sample_rate / 2.0
        lo  = np.clip(self.cfg.bandpass_low_hz  / nyq, 1e-4, 0.9999)
        hi  = np.clip(self.cfg.bandpass_high_hz / nyq, 1e-4, 0.9999)
        if lo >= hi:
            hi = min(lo + 0.01, 0.9999)
        self._bp_sos = signal.butter(4, [lo, hi], btype="band", output="sos")

    def _bandpass(self, x: np.ndarray) -> np.ndarray:
        """Band-pass: keep only voice-range frequencies."""
        return signal.sosfilt(self._bp_sos, x).astype(np.float32)

    def _preemphasis(self, x: np.ndarray) -> np.ndarray:
        """Spectral tilt – boosts high frequencies for clarity."""
        alpha = self.cfg.preemphasis_coef
        out = np.empty_like(x)
        out[0] = x[0]
        out[1:] = x[1:] - alpha * x[:-1]
        return out

    def _compress(self, x: np.ndarray) -> np.ndarray:
        """
        Simple feed-forward dynamic range compressor.
        Attenuates samples above threshold using ratio, with attack/release smoothing.
        """
        sr = self.sample_rate
        ratio     = self.cfg.compression_ratio
        thresh_db = self.cfg.compression_threshold_db
        thresh    = 10 ** (thresh_db / 20)

        attack_coef  = np.exp(-1.0 / (sr * self.cfg.compression_attack_ms  / 1000))
        release_coef = np.exp(-1.0 / (sr * self.cfg.compression_release_ms / 1000))

        gain_db = np.zeros(len(x), dtype=np.float32)
        level = 0.0

        for i, sample in enumerate(x):
            abs_s = abs(float(sample))
            if abs_s > level:
                level = attack_coef * level + (1 - attack_coef) * abs_s
            else:
                level = release_coef * level + (1 - release_coef) * abs_s

            if level > thresh:
                over_db = 20 * np.log10(level / (thresh + 1e-9))
                gain_db[i] = -(over_db * (1 - 1 / ratio))
            else:
                gain_db[i] = 0.0

        gain_linear = 10 ** (gain_db / 20)
        return (x * gain_linear).astype(np.float32)

    def _dereverberate(self, x: np.ndarray) -> np.ndarray:
        """
        Lightweight spectral subtraction-based de-reverberation.
        Estimates reverberation tail as a decayed version of spectrum and subtracts.
        """
        N = 2048
        hop = N // 2
        frames = []
        prev_magnitude = None
        decay = 0.85              # reverberation decay factor

        win = np.hanning(N)
        for start in range(0, len(x) - N, hop):
            frame = x[start : start + N] * win
            spectrum = np.fft.rfft(frame)
            magnitude = np.abs(spectrum)
            phase = np.angle(spectrum)

            if prev_magnitude is not None:
                reverb_est = decay * prev_magnitude
                magnitude = np.maximum(magnitude - 0.4 * reverb_est, 0.0)

            prev_magnitude = magnitude
            clean_spec = magnitude * np.exp(1j * phase)
            frames.append(np.fft.irfft(clean_spec))

        if not frames:
            return x

        # Overlap-add
        out = np.zeros(len(x), dtype=np.float32)
        norm = np.zeros(len(x), dtype=np.float32)
        for i, frame in enumerate(frames):
            start = i * hop
            end   = start + N
            if end > len(out):
                end = len(out)
                frame = frame[:end - start]
            out[start:end]  += frame * win[:end - start]
            norm[start:end] += win[:end - start] ** 2

        norm = np.where(norm > 1e-8, norm, 1.0)
        return (out / norm).astype(np.float32)

    def _normalise(self, x: np.ndarray) -> np.ndarray:
        """Peak normalise to target_peak_db."""
        peak = np.max(np.abs(x)) + 1e-9
       # target_linear = 10 ** (self.cfg.target_peak_db / 20)
        target_linear = 0.95 
        return (x * (target_linear / peak)).astype(np.float32)
