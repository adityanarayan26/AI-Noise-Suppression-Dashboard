import torch
import torchaudio
import os
from typing import Dict, Any

class NoiseSuppressionService:
    """
    Service to perform background noise suppression using a pre-trained ConvTasNet model.
    """
    
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
            # enhance() requires shape (batch, channels, time) = (1, 1, T)
            audio_tensor = torch.from_numpy(up).unsqueeze(0).unsqueeze(0)  # (1, 1, T_48k)
            with torch.no_grad():
                enhanced = enhance(self._df_model, self._df_state, audio_tensor)
            # enhanced shape is (1, T) or (1, 1, T) — squeeze all unit dims safely
            enhanced_np = enhanced.squeeze().numpy()
            if enhanced_np.ndim == 0:
                # scalar edge case — return silence
                return self._to_int16_bytes(np.zeros(orig_len, dtype=np.float32))

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
