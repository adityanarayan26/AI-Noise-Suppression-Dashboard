from app.services import noise_classification_service
import torch
import torchaudio
import os
import logging
import numpy as np
from typing import Dict, Any, Optional
from scipy.signal import resample_poly
from math import gcd


logger = logging.getLogger(__name__)

try:
    import df
    _df_available = True
except ImportError:
    _df_available = False

class NoiseSuppressionService:
    """
    Service to perform background noise suppression using DeepFilterNet.
    Falls back to spectral subtraction when DeepFilterNet is unavailable.
    """
    
    def __init__(self):
        self._suppression_enabled: bool = False
        self._frame_count: int = 0
        
        self.SAMPLE_RATE = 16000
        self._RESAMPLE_UP = 3
        self._RESAMPLE_DOWN = 1
        self._RESAMPLE_UP2 = 1
        self._RESAMPLE_DOWN2 = 3
        self.NOISE_PROFILE_FRAMES = 10
        self.ALPHA = 1.5
        self.SPECTRAL_FLOOR = 0.05

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
                logger.info("[DeepFilterNet] ✓ Model + state initialised successfully.")
            except Exception as exc:
                logger.error(
                    "[DeepFilterNet] Init failed: %s  — "
                    "falling back to spectral subtraction for this session.",
                    exc,
                )
        else:
            logger.warning(
                "[DeepFilterNet] 'df' package not importable. "
                "Install with: pip install deepfilternet"
            )

        # ── Fallback spectral-subtraction state ──────────────────────────────
        self._noise_profile: Optional[np.ndarray] = None
        self._profile_buffer: list[np.ndarray] = []

    # ─────────────────────────────────────────────────────────────────────────
    # Status / diagnostics
    # ─────────────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return a status dict describing the current engine state."""
        return {
            "engine": "deepfilternet" if self._use_df else "spectral_subtraction",
            "deepfilternet_available": _df_available,
            "deepfilternet_active": self._use_df,
            "suppression_enabled": self._suppression_enabled,
            "frame_count": self._frame_count,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────────────────────────────────────

    def process_audio(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """
        Process a full audio file from input_path and save the cleaned result to output_path.
        Uses DeepFilterNet when available, falls back to noisereduce.
        """
        try:
            import soundfile as sf

            # Load audio
            audio_data, sr = sf.read(input_path)

            # Convert to mono if needed
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)

            '''
            # Resample to 16 kHz if needed
            if sr != self.SAMPLE_RATE:
                #from scipy.signal import resample_poly
                from math import gcd
                g = gcd(self.SAMPLE_RATE, sr)
                audio_data = resample_poly(
                    audio_data, self.SAMPLE_RATE // g, sr // g
                ).astype(np.float32)
                sr = self.SAMPLE_RATE
            '''
            #from scipy.signal import resample_poly
            #from math import gcd

            # Resample to 16 kHz if needed
            if sr != self.SAMPLE_RATE:
                g = gcd(self.SAMPLE_RATE, sr)

                audio_data = resample_poly(
                    audio_data,
                    self.SAMPLE_RATE // g,  
                    sr // g
                ).astype(np.float32)

                sr = self.SAMPLE_RATE

            if self._use_df:
                try:
                    import torch

                    from df.enhance import enhance, init_df

                    # DeepFilterNet needs 48 kHz
                    up = resample_poly(
                        audio_data.astype(np.float32),
                        self._RESAMPLE_UP,
                        self._RESAMPLE_DOWN,
                    ).astype(np.float32)

                    # Create a fresh model+state for file processing to avoid
                    # polluting the live-stream LSTM state
                    file_model, file_state, _ = init_df()
                    file_model.eval()

                    audio_tensor = torch.from_numpy(up).float().unsqueeze(0)

                    with torch.no_grad():
                        enhanced = enhance(
                            file_model,
                            file_state, 
                            audio_tensor
                        )

                    enhanced_np = enhanced.squeeze().numpy()

                    # Downsample back to 16 kHz
                    reduced_noise = resample_poly(
                        enhanced_np,
                        self._RESAMPLE_UP2,
                        self._RESAMPLE_DOWN2,
                    ).astype(np.float32)

                    # Match original length
                    orig_len = len(audio_data)
                    if len(reduced_noise) > orig_len:
                        reduced_noise = reduced_noise[:orig_len]
                    elif len(reduced_noise) < orig_len:
                        reduced_noise = np.pad(
                            reduced_noise, (0, orig_len - len(reduced_noise))
                        )

                    logger.info("[DeepFilterNet] File processed successfully.")

                except Exception as e:
                    logger.warning(
                        "[DeepFilterNet] File processing failed (%s), "
                        "falling back to noisereduce.",
                        e,
                    )
                    import noisereduce as nr
                    reduced_noise = nr.reduce_noise(
                        y=audio_data, sr=sr, stationary=True, prop_decrease=0.85
                    )
            else:
                import noisereduce as nr
                reduced_noise = nr.reduce_noise(
                    y=audio_data, sr=sr, stationary=True, prop_decrease=0.85
                )

            # Save cleaned audio
            sf.write(output_path, reduced_noise, sr)

            return {
                "success": True,
                "error": None,
                "clean_audio_url": output_path,
            }
        except Exception as e:
            logger.error(f"Error processing file audio: {e}")
            return {
                "success": False,
                "error": str(e),
                "clean_audio_url": "",
            }

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
            self._frame_count += 1
            return self._to_int16_bytes(samples)

        if self._use_df:
            result = self._process_deepfilter(samples)
        else:
            result = self._process_spectral(samples)

        self._frame_count += 1
        return result

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
            #audio_tensor = torch.from_numpy(up).unsqueeze(0).unsqueeze(0)  # (1, 1, T_48k)

            audio_tensor = torch.from_numpy(up).float().unsqueeze(0)
            with torch.no_grad():
                logger.info(f"DF input shape: {audio_tensor.shape}")
                
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
