"""
AudioQualityService
-------------------
Measures audio quality before/after processing and orchestrates the full
noise-suppression pipeline.

Metrics:
  - RMS & peak levels (dBFS)
  - SNR estimate (dB)
  - PESQ-like MOS score (simplified wideband estimate)
  - Spectral distortion
  - Clipping detection
  - SI-SDR (scale-invariant SDR) when reference is available

Orchestration:
  AudioQualityService.process(audio) runs:
    NoiseClassificationService → NoiseSuppressionService → VoiceClarityService
  and returns both cleaned audio and a QualityReport.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from scipy import signal


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class QualityMetrics:
    rms_db: float               # RMS level in dBFS
    peak_db: float              # Peak level in dBFS
    snr_db: float               # Estimated SNR (dB)
    mos_estimate: float         # Mean Opinion Score estimate (1–5)
    spectral_distortion: float  # Average spectral distortion vs original (dB), 0 if no ref
    clipping_ratio: float       # Fraction of samples clipped (>0.999)
    dynamic_range_db: float     # Crest factor (peak - RMS in dB)
    si_sdr_db: float            # Scale-invariant SDR vs reference (dB), NaN if no ref

    def __str__(self) -> str:
        return (
            f"RMS={self.rms_db:.1f}dBFS  Peak={self.peak_db:.1f}dBFS  "
            f"SNR={self.snr_db:.1f}dB  MOS≈{self.mos_estimate:.2f}  "
            f"Clipping={self.clipping_ratio*100:.2f}%  "
            f"SI-SDR={self.si_sdr_db:.1f}dB"
        )


@dataclass
class QualityReport:
    before: QualityMetrics
    after: QualityMetrics
    noise_type: str
    noise_confidence: float
    processing_time_ms: float
    snr_improvement_db: float
    mos_improvement: float
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "━━━━  Audio Quality Report  ━━━━",
            f"Noise detected : {self.noise_type} (confidence {self.noise_confidence:.0%})",
            f"Processing time: {self.processing_time_ms:.1f} ms",
            "",
            f"{'Metric':<24} {'Before':>10} {'After':>10} {'Δ':>10}",
            "─" * 56,
            f"{'SNR (dB)':<24} {self.before.snr_db:>10.1f} {self.after.snr_db:>10.1f} "
            f"{self.snr_improvement_db:>+10.1f}",
            f"{'MOS estimate':<24} {self.before.mos_estimate:>10.2f} "
            f"{self.after.mos_estimate:>10.2f} {self.mos_improvement:>+10.2f}",
            f"{'RMS (dBFS)':<24} {self.before.rms_db:>10.1f} {self.after.rms_db:>10.1f}",
            f"{'Peak (dBFS)':<24} {self.before.peak_db:>10.1f} {self.after.peak_db:>10.1f}",
            f"{'Clipping %':<24} {self.before.clipping_ratio*100:>10.2f} "
            f"{self.after.clipping_ratio*100:>10.2f}",
        ]
        if self.warnings:
            lines += ["", "⚠ Warnings:"] + [f"  • {w}" for w in self.warnings]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AudioQualityService
# ---------------------------------------------------------------------------

class AudioQualityService:
    """
    Measures audio quality and orchestrates the full processing pipeline:
      classify → suppress → clarity → measure
    """

    CLIP_THRESHOLD: float = 0.999

    def __init__(self, sample_rate: int = 48_000):
        self.sample_rate = sample_rate

    # ------------------------------------------------------------------
    # Full pipeline orchestration
    # ------------------------------------------------------------------

    def process(
        self,
        audio: np.ndarray,
        input_sr: int = 48_000,
        attenuation_db: float = 100.0,
        clarity_settings=None,
    ) -> tuple[np.ndarray, QualityReport]:
        """
        Run the complete noise suppression pipeline.

        Args:
            audio:            Raw input audio (float32, mono or stereo).
            input_sr:         Sample rate of *audio*.
            attenuation_db:   DeepFilterNet noise attenuation limit.
            clarity_settings: VoiceClaritySettings instance (optional).

        Returns:
            (cleaned_audio, QualityReport)
        """
        # Import here to avoid circular dependencies at module level
        from noise_classification_service import NoiseClassificationService
        from noise_suppression_service import NoiseSuppressionService
        from voice_clarity_service import VoiceClarityService, VoiceClaritySettings

        t0 = time.perf_counter()

        # 1. Measure input quality
        before_metrics = self.measure(audio, sample_rate=input_sr)

        # 2. Classify noise
        classifier  = NoiseClassificationService(sample_rate=input_sr)
        mono_audio  = audio if audio.ndim == 1 else audio.mean(axis=0)
        cls_result  = classifier.classify(mono_audio)

        # 3. Suppress noise (DeepFilterNet3)
        suppressor  = NoiseSuppressionService(attenuation_limit_db=attenuation_db)
        suppressed  = suppressor.process_array(audio, input_sr=input_sr)

        # 4. Voice clarity post-processing
        settings = clarity_settings or VoiceClaritySettings()
        clarifier = VoiceClarityService(sample_rate=suppressor.sample_rate, settings=settings)
        cleaned   = clarifier.enhance(suppressed)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # 5. Measure output quality
        after_metrics = self.measure(cleaned, reference=audio if audio.ndim == 1 else None,
                                     sample_rate=suppressor.sample_rate)

        # 6. Build report
        warnings = []
        if before_metrics.clipping_ratio > 0.001:
            warnings.append(f"Input clipping detected ({before_metrics.clipping_ratio*100:.1f}% samples)")
        if after_metrics.mos_estimate < 2.5:
            warnings.append("Output MOS below acceptable threshold (< 2.5)")
        if cls_result.snr_db < 5:
            warnings.append("Very low input SNR – suppression may introduce artefacts")

        report = QualityReport(
            before            = before_metrics,
            after             = after_metrics,
            noise_type        = cls_result.noise_type.value,
            noise_confidence  = cls_result.confidence,
            processing_time_ms= elapsed_ms,
            snr_improvement_db= after_metrics.snr_db - before_metrics.snr_db,
            mos_improvement   = after_metrics.mos_estimate - before_metrics.mos_estimate,
            warnings          = warnings,
        )

        return cleaned, report

    # ------------------------------------------------------------------
    # Quality measurement
    # ------------------------------------------------------------------

    def measure(
        self,
        audio: np.ndarray,
        reference: Optional[np.ndarray] = None,
        sample_rate: Optional[int] = None,
    ) -> QualityMetrics:
        """
        Compute quality metrics for *audio*.

        Args:
            audio:      float32 array [samples] or [channels, samples].
            reference:  Optional clean reference for SI-SDR / spectral distortion.
            sample_rate: Override instance sample rate.

        Returns:
            QualityMetrics
        """
        sr = sample_rate or self.sample_rate
        mono = audio if audio.ndim == 1 else audio.mean(axis=0)
        mono = mono.astype(np.float32)

        rms_db  = self._rms_db(mono)
        peak_db = self._peak_db(mono)
        snr_db  = self._estimate_snr(mono)
        clipping= self._clipping_ratio(mono)
        dr_db   = peak_db - rms_db

        # MOS estimate
        mos = self._estimate_mos(mono, sr, snr_db)

        # Reference-dependent metrics
        spec_dist = 0.0
        si_sdr    = float("nan")
        if reference is not None:
            ref = reference.astype(np.float32)
            ref = ref if ref.ndim == 1 else ref.mean(axis=0)
            # Align lengths
            min_len = min(len(mono), len(ref))
            mono_a, ref_a = mono[:min_len], ref[:min_len]
            spec_dist = self._spectral_distortion(mono_a, ref_a)
            si_sdr    = self._si_sdr(mono_a, ref_a)

        return QualityMetrics(
            rms_db              = rms_db,
            peak_db             = peak_db,
            snr_db              = snr_db,
            mos_estimate        = mos,
            spectral_distortion = spec_dist,
            clipping_ratio      = clipping,
            dynamic_range_db    = dr_db,
            si_sdr_db           = si_sdr,
        )

    # ------------------------------------------------------------------
    # Individual metric helpers
    # ------------------------------------------------------------------

    def _rms_db(self, audio: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(audio ** 2) + 1e-12))
        return 20 * np.log10(rms)

    def _peak_db(self, audio: np.ndarray) -> float:
        peak = float(np.max(np.abs(audio)) + 1e-12)
        return 20 * np.log10(peak)

    def _clipping_ratio(self, audio: np.ndarray) -> float:
        return float(np.mean(np.abs(audio) > self.CLIP_THRESHOLD))

    def _estimate_snr(self, audio: np.ndarray, frame_ms: int = 20) -> float:
        """Min-statistics SNR estimator."""
        frame_size = int(self.sample_rate * frame_ms / 1000)
        frames = [
            audio[i : i + frame_size]
            for i in range(0, len(audio) - frame_size, frame_size)
        ]
        if len(frames) < 2:
            return 0.0
        energies = np.array([np.mean(f ** 2) for f in frames])
        noise_floor = np.percentile(energies, 10) + 1e-12
        signal_peak = np.percentile(energies, 90) + 1e-12
        return float(np.clip(10 * np.log10(signal_peak / noise_floor), -10, 60))

    def _estimate_mos(self, audio: np.ndarray, sr: int, snr_db: float) -> float:
        """
        Simplified MOS-LQO estimate using spectral and energy features.
        This is a heuristic approximation; for production use PESQ/DNSMOS.
        Range: 1.0 (bad) – 5.0 (excellent).
        """
        # Component 1: SNR contribution (0 → 2.5 points)
        snr_score = np.clip(snr_db / 24, 0, 1) * 2.5

        # Component 2: Spectral naturalness (0 → 1.5 points)
        N = min(len(audio), 8192)
        spectrum = np.abs(np.fft.rfft(audio[:N] * np.hanning(N)))
        freqs    = np.fft.rfftfreq(N, d=1.0 / sr)
        # Voice band presence
        voice_mask = (freqs >= 100) & (freqs <= 4000)
        total_e    = np.sum(spectrum ** 2) + 1e-9
        voice_e    = np.sum(spectrum[voice_mask] ** 2) / total_e
        spec_score = np.clip(voice_e * 1.5, 0, 1.5)

        # Component 3: Clipping penalty (0 → -1 point)
        clip_penalty = -np.clip(self._clipping_ratio(audio) * 10, 0, 1.0)

        mos = 1.0 + snr_score + spec_score + clip_penalty
        return float(np.clip(mos, 1.0, 5.0))

    def _spectral_distortion(self, enhanced: np.ndarray, reference: np.ndarray) -> float:
        """Average log-spectral distortion in dB."""
        N = min(len(enhanced), len(reference), 8192)
        E = np.abs(np.fft.rfft(enhanced[:N])) + 1e-9
        R = np.abs(np.fft.rfft(reference[:N])) + 1e-9
        lsd = np.mean((20 * np.log10(E / R)) ** 2) ** 0.5
        return float(lsd)

    def _si_sdr(self, estimate: np.ndarray, reference: np.ndarray) -> float:
        """Scale-invariant Signal-to-Distortion Ratio."""
        ref  = reference - np.mean(reference)
        est  = estimate  - np.mean(estimate)
        alpha = np.dot(est, ref) / (np.dot(ref, ref) + 1e-9)
        target   = alpha * ref
        residual = est - target
        si_sdr   = 10 * np.log10(
            (np.sum(target ** 2) + 1e-9) / (np.sum(residual ** 2) + 1e-9)
        )
        return float(np.clip(si_sdr, -30, 40))

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def compare(
        self, before: np.ndarray, after: np.ndarray, sr: Optional[int] = None
    ) -> dict:
        """Return a simple dict comparing before/after metrics."""
        m_b = self.measure(before, sample_rate=sr)
        m_a = self.measure(after,  reference=before if before.ndim == 1 else None,
                           sample_rate=sr)
        return {
            "snr_before_db":    m_b.snr_db,
            "snr_after_db":     m_a.snr_db,
            "snr_improvement":  m_a.snr_db - m_b.snr_db,
            "mos_before":       m_b.mos_estimate,
            "mos_after":        m_a.mos_estimate,
            "mos_improvement":  m_a.mos_estimate - m_b.mos_estimate,
            "si_sdr_db":        m_a.si_sdr_db,
            "spectral_dist_db": m_a.spectral_distortion,
        }
