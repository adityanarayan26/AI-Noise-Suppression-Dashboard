"""
NoiseSuppressionService — DeepFilterNet-powered real-time noise suppression.

Architecture
------------
* Model loading  : DeepFilterNet model weights are downloaded once (~65 MB) on first
                   use and cached by the library in ~/.cache/DeepFilterNet. Subsequent
                   starts load from disk in <2 s.
* Per-connection : Each WebSocket connection (each NoiseSuppressionService instance)
                   gets its own model + DFState so LSTM hidden states don't bleed
                   between simultaneous sessions.
* Sample rates   : Frontend sends 16 kHz Int16 PCM. DeepFilterNet requires 48 kHz.
                   We upsample (3×) before the model and downsample (÷3) after.
                   scipy.signal.resample_poly is used for high-quality polyphase resampling.
* Fallback       : If deepfilternet / torch is not installed, the service transparently
                   falls back to the original spectral-subtraction algorithm and logs a
                   warning — the rest of the application continues unmodified.

Public interface (unchanged from the previous implementation)
-------------------------------------------------------------
  process(pcm_bytes)         → bytes   # Int16 PCM in, Int16 PCM out
  set_suppression(enabled)            # toggle suppression on/off
  reset_noise_profile()               # reset LSTM/noise state between sessions
  compute_snr_db(pcm_bytes)  → float  # SNR estimate on raw frame
"""

import logging
import threading
import numpy as np
from scipy.signal import resample_poly
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Module-level state: first-import warm-up flag and lock
# ─────────────────────────────────────────────────────────────────────────────
_warmup_done = False
_warmup_lock = threading.Lock()
_df_available = False   # True once a successful import is confirmed


def _warmup_deepfilter() -> bool:
    """
    Attempt to import deepfilternet and download/cache the model weights.
    Called once at module load time (or on first instantiation).
    Returns True if DeepFilterNet is available.
    """
    global _warmup_done, _df_available
    if _warmup_done:
        return _df_available
    with _warmup_lock:
        if _warmup_done:
            return _df_available
        try:
            # Importing triggers the one-time model download if not already cached.
            from df.enhance import init_df  # noqa: F401
            import torch  # noqa: F401
            _df_available = True
            logger.info("[DeepFilterNet] ✓ Package available — model will load on first connection.")
        except ImportError as exc:
            logger.warning(
                "[DeepFilterNet] ✗ Not installed (%s). "
                "Falling back to spectral subtraction. "
                "Run: pip install deepfilternet torch",
                exc,
            )
            _df_available = False
        _warmup_done = True
    return _df_available


# Run warm-up at import time (non-blocking; just checks imports)
_warmup_deepfilter()


# ─────────────────────────────────────────────────────────────────────────────
class NoiseSuppressionService:
    """
    Drop-in replacement for the spectral-subtraction NoiseSuppressionService.

    When DeepFilterNet is available, each instance loads its own model + DFState
    so concurrent WebSocket sessions are fully isolated.
    """

    # Wire-protocol sample rate (what the frontend sends)
    SAMPLE_RATE = 16000
    # DeepFilterNet native sample rate
    DF_SAMPLE_RATE = 48000
    # Up/down-sample ratio (must be integer multiple)
    _RESAMPLE_UP = 3    # 16000 × 3 = 48000
    _RESAMPLE_DOWN = 1  # denominator for up-direction
    _RESAMPLE_UP2 = 1   # numerator for down-direction
    _RESAMPLE_DOWN2 = 3 # 48000 ÷ 3 = 16000

    # ── Fallback spectral-subtraction constants ──
    NOISE_PROFILE_FRAMES = 10
    ALPHA = 2.0
    SPECTRAL_FLOOR = 0.002

    def __init__(self):
        self._suppression_enabled: bool = True
        self._frame_count: int = 0

        # ── Try to initialise DeepFilterNet ──────────────────────────────────
        self._use_df: bool = False
        self._df_model = None
        self._df_state = None

        if _df_available:
            try:
                from df.enhance import init_df
                # Each instance gets a completely independent model + LSTM state.
                # torch.jit.load is fast after the first OS page-cache warm-up.
                self._df_model, self._df_state, _ = init_df()
                self._df_model.eval()
                self._use_df = True
                logger.info("[DeepFilterNet] ✓ Per-connection model+state initialised.")
            except Exception as exc:
                logger.error(
                    "[DeepFilterNet] Per-connection init failed (%s). "
                    "Using spectral subtraction for this session.",
                    exc,
                )

        # ── Fallback spectral-subtraction state ──────────────────────────────
        self._noise_profile: Optional[np.ndarray] = None
        self._profile_buffer: list[np.ndarray] = []

    # ─────────────────────────────────────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────────────────────────────────────

    def set_suppression(self, enabled: bool) -> None:
        self._suppression_enabled = enabled

    def reset_noise_profile(self) -> None:
        """
        Reset all internal state.
        Call this when the client sends control byte 0x02 (new-session signal).
        """
        if self._use_df and self._df_state is not None:
            try:
                self._df_state.reset()
                logger.debug("[DeepFilterNet] DFState reset.")
            except Exception as exc:
                logger.warning("[DeepFilterNet] state.reset() failed: %s", exc)

        # Reset fallback state regardless
        self._noise_profile = None
        self._profile_buffer = []
        self._frame_count = 0

    def process(self, pcm_bytes: bytes) -> bytes:
        """
        Accepts raw Int16 PCM bytes at SAMPLE_RATE (16 kHz).
        Returns noise-suppressed Int16 PCM bytes at the same rate.
        """
        samples = (
            np.frombuffer(pcm_bytes, dtype=np.int16)
              .astype(np.float32) / 32768.0
        )

        if not self._suppression_enabled:
            return self._to_int16_bytes(samples)

        if self._use_df:
            return self._process_deepfilter(samples)
        else:
            return self._process_spectral(samples)

    def compute_snr_db(self, pcm_bytes: bytes) -> float:
        """
        Estimate Signal-to-Noise Ratio in dB for the raw (unsuppressed) frame.
        Uses energy ratio of speech band (300–3400 Hz) vs. everything else.
        Returns SNR in dB, clamped to [-20, +60].
        """
        samples = (
            np.frombuffer(pcm_bytes, dtype=np.int16)
              .astype(np.float32) / 32768.0
        )
        spectrum = np.fft.rfft(samples)
        magnitude = np.abs(spectrum)

        freq_bins = np.fft.rfftfreq(len(samples), d=1.0 / self.SAMPLE_RATE)
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

    # ─────────────────────────────────────────────────────────────────────────
    # Private: DeepFilterNet path
    # ─────────────────────────────────────────────────────────────────────────

    def _process_deepfilter(self, samples: np.ndarray) -> bytes:
        try:
            import torch
            from df.enhance import enhance

            orig_len = len(samples)

            # ── 1. Upsample 16 kHz → 48 kHz ──────────────────────────────
            up = resample_poly(samples, self._RESAMPLE_UP, self._RESAMPLE_DOWN).astype(
                np.float32
            )

            # ── 2. DeepFilterNet enhancement (stateful — preserves LSTM state) ──
            audio_tensor = torch.from_numpy(up).unsqueeze(0)  # (1, T_48k)
            with torch.no_grad():
                enhanced = enhance(self._df_model, self._df_state, audio_tensor)
            enhanced_np = enhanced.squeeze(0).numpy()

            # ── 3. Downsample 48 kHz → 16 kHz ────────────────────────────
            down = resample_poly(enhanced_np, self._RESAMPLE_UP2, self._RESAMPLE_DOWN2).astype(
                np.float32
            )

            # ── 4. Trim / zero-pad to match original frame length exactly ──
            if len(down) > orig_len:
                down = down[:orig_len]
            elif len(down) < orig_len:
                down = np.pad(down, (0, orig_len - len(down)))

            return self._to_int16_bytes(down)

        except Exception as exc:
            # On any runtime failure, disable DF for this session and fall back.
            logger.error(
                "[DeepFilterNet] Runtime error (%s). "
                "Switching to spectral subtraction for this session.",
                exc,
            )
            self._use_df = False
            return self._process_spectral(samples)

    # ─────────────────────────────────────────────────────────────────────────
    # Private: spectral-subtraction fallback
    # ─────────────────────────────────────────────────────────────────────────

    def _process_spectral(self, samples: np.ndarray) -> bytes:
        """Classic spectral subtraction — used when DeepFilterNet is unavailable."""
        from numpy.fft import rfft, irfft

        spectrum = rfft(samples)
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)

        # Calibration phase: collect initial frames to estimate noise floor
        if self._noise_profile is None:
            self._profile_buffer.append(magnitude)
            if len(self._profile_buffer) >= self.NOISE_PROFILE_FRAMES:
                self._noise_profile = np.mean(self._profile_buffer, axis=0)
            return self._to_int16_bytes(samples)

        # H(k) = max(|X(k)| − α|N(k)|, floor·|X(k)|)
        suppressed_mag = np.maximum(
            magnitude - self.ALPHA * self._noise_profile,
            self.SPECTRAL_FLOOR * magnitude,
        )
        suppressed_spectrum = suppressed_mag * np.exp(1j * phase)
        suppressed_samples = irfft(suppressed_spectrum, n=len(samples))

        # Slow noise-floor adaptation (5 % per frame)
        self._noise_profile = (
            0.95 * self._noise_profile + 0.05 * magnitude
        )
        self._frame_count += 1

        return self._to_int16_bytes(suppressed_samples)

    # ─────────────────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_int16_bytes(samples: np.ndarray) -> bytes:
        clipped = np.clip(samples, -1.0, 1.0)
        return (clipped * 32767).astype(np.int16).tobytes()
