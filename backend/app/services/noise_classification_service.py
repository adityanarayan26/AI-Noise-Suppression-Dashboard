"""
NoiseClassificationService
--------------------------
Classifies audio noise type using YAMNet (Yet Another Audio MobileNet),
a lightweight MobileNet-based model pretrained on AudioSet (521 classes).

Supports: background_noise, traffic, wind, keyboard, fan, music, speech, silence.

Install deps:
    pip install tensorflow tensorflow-hub numpy

Optional (higher-quality resampling):
    pip install resampy

YAMNet weights (~3.7 MB) are downloaded automatically from TF Hub on first use.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Optional heavy imports — deferred for test environments that mock inference.
# ---------------------------------------------------------------------------
try:
    import tensorflow as tf
    import tensorflow_hub as hub
    _TF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public types  (API-compatible with the original service)
# ---------------------------------------------------------------------------

class NoiseType(str, Enum):
    SILENCE          = "silence"
    SPEECH           = "speech"
    BACKGROUND_NOISE = "background_noise"
    TRAFFIC          = "traffic"
    WIND             = "wind"
    KEYBOARD         = "keyboard"
    FAN              = "fan"
    MUSIC            = "music"
    UNKNOWN          = "unknown"


@dataclass
class ClassificationResult:
    noise_type:       NoiseType
    confidence:       float   # 0.0 – 1.0  (normalised bucket score)
    snr_db:           float   # estimated SNR via min-statistics
    rms_db:           float   # RMS energy in dBFS
    dominant_freq_hz: float   # spectral peak frequency


# ---------------------------------------------------------------------------
# YAMNet AudioSet index → NoiseType mapping
#
# Indices come from the official class map (521 classes):
#   https://raw.githubusercontent.com/tensorflow/models/master/research/
#          audioset/yamnet/yamnet_class_map.csv
#
# Every index that belongs to a bucket is listed explicitly — no substring
# matching, no false positives from coincidental label overlaps.
# ---------------------------------------------------------------------------

# fmt: off
_YAMNET_INDEX_TO_NOISE_TYPE: dict[int, NoiseType] = {

    # ── Silence ──────────────────────────────────────────────────────────
    494: NoiseType.SILENCE,                     # Silence

    # ── Speech ───────────────────────────────────────────────────────────
      0: NoiseType.SPEECH,                      # Speech
      1: NoiseType.SPEECH,                      # Child speech, kid speaking
      5: NoiseType.SPEECH,                      # Speech synthesizer
      6: NoiseType.SPEECH,                      # Shout
     10: NoiseType.SPEECH,                      # Children shouting
     12: NoiseType.SPEECH,                      # Whispering
     65: NoiseType.SPEECH,                      # Hubbub, speech noise, speech babble

    # ── Music ─────────────────────────────────────────────────────────────
    132: NoiseType.MUSIC,                       # Music
    133: NoiseType.MUSIC,                       # Musical instrument
    211: NoiseType.MUSIC,                       # Pop music
    212: NoiseType.MUSIC,                       # Hip hop music
    214: NoiseType.MUSIC,                       # Rock music
    222: NoiseType.MUSIC,                       # Soul music
    225: NoiseType.MUSIC,                       # Swing music
    228: NoiseType.MUSIC,                       # Folk music
    229: NoiseType.MUSIC,                       # Middle Eastern music
    232: NoiseType.MUSIC,                       # Classical music
    234: NoiseType.MUSIC,                       # Electronic music
    235: NoiseType.MUSIC,                       # House music
    240: NoiseType.MUSIC,                       # Electronic dance music
    241: NoiseType.MUSIC,                       # Ambient music
    242: NoiseType.MUSIC,                       # Trance music
    243: NoiseType.MUSIC,                       # Music of Latin America
    244: NoiseType.MUSIC,                       # Salsa music
    247: NoiseType.MUSIC,                       # Music for children
    248: NoiseType.MUSIC,                       # New-age music
    249: NoiseType.MUSIC,                       # Vocal music
    251: NoiseType.MUSIC,                       # Music of Africa
    253: NoiseType.MUSIC,                       # Christian music
    254: NoiseType.MUSIC,                       # Gospel music
    255: NoiseType.MUSIC,                       # Music of Asia
    256: NoiseType.MUSIC,                       # Carnatic music
    257: NoiseType.MUSIC,                       # Music of Bollywood
    259: NoiseType.MUSIC,                       # Traditional music
    260: NoiseType.MUSIC,                       # Independent music
    262: NoiseType.MUSIC,                       # Background music
    263: NoiseType.MUSIC,                       # Theme music
    264: NoiseType.MUSIC,                       # Jingle (music)
    265: NoiseType.MUSIC,                       # Soundtrack music
    267: NoiseType.MUSIC,                       # Video game music
    268: NoiseType.MUSIC,                       # Christmas music
    269: NoiseType.MUSIC,                       # Dance music
    270: NoiseType.MUSIC,                       # Wedding music
    271: NoiseType.MUSIC,                       # Happy music
    272: NoiseType.MUSIC,                       # Sad music
    273: NoiseType.MUSIC,                       # Tender music
    274: NoiseType.MUSIC,                       # Exciting music
    275: NoiseType.MUSIC,                       # Angry music
    276: NoiseType.MUSIC,                       # Scary music
     24: NoiseType.MUSIC,                       # Singing
     29: NoiseType.MUSIC,                       # Child singing
     30: NoiseType.MUSIC,                       # Synthetic singing
     32: NoiseType.MUSIC,                       # Humming (musical)

    # ── Traffic ───────────────────────────────────────────────────────────
    294: NoiseType.TRAFFIC,                     # Vehicle
    300: NoiseType.TRAFFIC,                     # Motor vehicle (road)
    301: NoiseType.TRAFFIC,                     # Car
    302: NoiseType.TRAFFIC,                     # Vehicle horn, car horn, honking
    304: NoiseType.TRAFFIC,                     # Car alarm
    305: NoiseType.TRAFFIC,                     # Power windows, electric windows
    308: NoiseType.TRAFFIC,                     # Car passing by
    309: NoiseType.TRAFFIC,                     # Race car, auto racing
    310: NoiseType.TRAFFIC,                     # Truck
    312: NoiseType.TRAFFIC,                     # Air horn, truck horn
    315: NoiseType.TRAFFIC,                     # Bus
    316: NoiseType.TRAFFIC,                     # Emergency vehicle
    317: NoiseType.TRAFFIC,                     # Police car (siren)
    319: NoiseType.TRAFFIC,                     # Fire engine, fire truck (siren)
    320: NoiseType.TRAFFIC,                     # Motorcycle
    321: NoiseType.TRAFFIC,                     # Traffic noise, roadway noise

    # ── Wind ──────────────────────────────────────────────────────────────
    277: NoiseType.WIND,                        # Wind
    279: NoiseType.WIND,                        # Wind noise (microphone)
    201: NoiseType.WIND,                        # Wind chime

    # ── Fan / HVAC ────────────────────────────────────────────────────────
    406: NoiseType.FAN,                         # Mechanical fan
    407: NoiseType.FAN,                         # Air conditioning
    490: NoiseType.FAN,                         # Hum
    510: NoiseType.FAN,                         # Mains hum
    514: NoiseType.FAN,                         # White noise
    515: NoiseType.FAN,                         # Pink noise

    # ── Keyboard / typing ─────────────────────────────────────────────────
    378: NoiseType.KEYBOARD,                    # Typing
    380: NoiseType.KEYBOARD,                    # Computer keyboard
    485: NoiseType.KEYBOARD,                    # Clicking
    486: NoiseType.KEYBOARD,                    # Clickety-clack

    # ── Generic background noise ──────────────────────────────────────────
    507: NoiseType.BACKGROUND_NOISE,            # Noise
    508: NoiseType.BACKGROUND_NOISE,            # Environmental noise
    509: NoiseType.BACKGROUND_NOISE,            # Static
     79: NoiseType.BACKGROUND_NOISE,            # Hiss
}
# fmt: on


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class NoiseClassificationService:
    """
    Classifies the dominant noise type in an audio chunk using YAMNet,
    a MobileNet-based model pretrained on AudioSet (521 classes).

    Parameters
    ----------
    sample_rate : int
        Native sample-rate of the incoming audio.  Audio is resampled to
        16 kHz internally (YAMNet requirement).
    silence_threshold_db : float
        RMS level below which audio is classified as silence without running
        inference.  Defaults to -60 dBFS.
    min_confidence : float
        Normalised bucket confidence below which the result is UNKNOWN.
        Defaults to 0.20.
    """

    YAMNET_SAMPLE_RATE: int = 16_000   # YAMNet expects 16 kHz mono
    YAMNET_HUB_URL: str = "https://tfhub.dev/google/yamnet/1"

    # Spectral diagnostics
    FRAME_SIZE: int = 1024
    HOP_SIZE:   int = 512

    def __init__(
        self,
        sample_rate:          int   = 48_000,
        silence_threshold_db: float = -60.0,
        min_confidence:       float = 0.20,
    ) -> None:
        if not _TF_AVAILABLE:
            raise ImportError(
                "TensorFlow dependencies not installed.\n"
                "Run: pip install tensorflow tensorflow-hub"
            )

        self.sample_rate          = sample_rate
        self.silence_threshold_db = silence_threshold_db
        self.min_confidence       = min_confidence

        # Load YAMNet from TF Hub (downloads ~3.7 MB on first call).
        self._model = hub.load(self.YAMNET_HUB_URL)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, audio: np.ndarray) -> ClassificationResult:
        """
        Classify the noise type in *audio* (mono float32, shape [N]).

        Parameters
        ----------
        audio : np.ndarray
            1-D (or 2-D stereo) float32 array in [-1, 1].

        Returns
        -------
        ClassificationResult
        """
        # ── Pre-processing ────────────────────────────────────────────
        if audio.ndim > 1:
            audio = audio.mean(axis=0)
        audio = audio.astype(np.float32)

        # ── Diagnostics (computed on native-rate audio) ───────────────
        rms    = self._rms(audio)
        rms_db = float(20 * np.log10(rms + 1e-9))

        # Fast-path: silence — skip inference entirely
        if rms_db < self.silence_threshold_db:
            return ClassificationResult(
                noise_type=NoiseType.SILENCE,
                confidence=0.95,
                snr_db=0.0,
                rms_db=round(rms_db, 2),
                dominant_freq_hz=0.0,
            )

        spectrum, freqs = self._magnitude_spectrum(audio)
        dom_freq        = self._dominant_frequency(spectrum, freqs)
        snr_db          = self._estimate_snr(audio)

        # ── Resample → 16 kHz for YAMNet ─────────────────────────────
        audio_16k = self._resample(audio)

        # ── YAMNet inference ──────────────────────────────────────────
        # Returns:
        #   scores  – (num_frames, 521) per-frame class scores
        #   embeddings – (num_frames, 1024) MobileNet embeddings
        #   spectrogram – (num_frames, 64) log-mel spectrogram
        scores, _embeddings, _spectrogram = self._model(audio_16k)

        # Average scores across all frames → (521,)
        mean_scores: np.ndarray = tf.reduce_mean(scores, axis=0).numpy()

        # ── Map YAMNet scores → NoiseType buckets ─────────────────────
        noise_type, confidence = self._aggregate_scores(mean_scores)

        if confidence < self.min_confidence:
            noise_type = NoiseType.UNKNOWN
            confidence = float(np.max(mean_scores))

        return ClassificationResult(
            noise_type=noise_type,
            confidence=round(float(confidence), 3),
            snr_db=round(snr_db, 2),
            rms_db=round(rms_db, 2),
            dominant_freq_hz=round(dom_freq, 1),
        )

    def classify_batch(self, chunks: list[np.ndarray]) -> list[ClassificationResult]:
        """Classify a list of audio chunks sequentially."""
        return [self.classify(c) for c in chunks]

    # ------------------------------------------------------------------
    # YAMNet helpers
    # ------------------------------------------------------------------

    def _resample(self, audio: np.ndarray) -> tf.Tensor:
        """
        Resample *audio* from self.sample_rate → YAMNET_SAMPLE_RATE.
        Uses resampy when available (polyphase, high quality), otherwise
        falls back to tf.signal linear interpolation.
        """
        if self.sample_rate == self.YAMNET_SAMPLE_RATE:
            return tf.constant(audio, dtype=tf.float32)

        try:
            import resampy
            audio_16k = resampy.resample(
                audio, self.sample_rate, self.YAMNET_SAMPLE_RATE
            ).astype(np.float32)
            return tf.constant(audio_16k, dtype=tf.float32)
        except ImportError:
            pass

        # TF-native fallback: resize 1-D signal via linear interpolation
        n_out = int(len(audio) * self.YAMNET_SAMPLE_RATE / self.sample_rate)
        t = tf.constant(audio[None, :, None], dtype=tf.float32)   # (1, N, 1)
        t = tf.image.resize(t, [1, n_out], method="bilinear")
        return tf.squeeze(t, axis=[0, 2])

    def _aggregate_scores(
        self, scores: np.ndarray
    ) -> tuple[NoiseType, float]:
        """
        Sum YAMNet per-class scores into NoiseType buckets.
        Confidence is the winning bucket's share of all mapped scores.
        """
        bucket_scores: dict[NoiseType, float] = {t: 0.0 for t in NoiseType}
        for idx, noise_type in _YAMNET_INDEX_TO_NOISE_TYPE.items():
            if idx < len(scores):
                bucket_scores[noise_type] += float(scores[idx])

        bucket_scores.pop(NoiseType.UNKNOWN, None)   # UNKNOWN is a fallback only

        total = sum(bucket_scores.values()) + 1e-9
        if total <= 1e-9 or max(bucket_scores.values()) == 0.0:
            return NoiseType.UNKNOWN, 0.0

        best_type  = max(bucket_scores, key=lambda k: bucket_scores[k])
        confidence = bucket_scores[best_type] / total
        return best_type, min(float(confidence), 1.0)

    # ------------------------------------------------------------------
    # Spectral diagnostic helpers  (unchanged from original)
    # ------------------------------------------------------------------

    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(audio ** 2)))

    def _magnitude_spectrum(
        self, audio: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        N        = min(len(audio), 8192)
        windowed = audio[:N] * np.hanning(N)
        fft      = np.abs(np.fft.rfft(windowed))
        freqs    = np.fft.rfftfreq(N, d=1.0 / self.sample_rate)
        return fft, freqs

    def _dominant_frequency(
        self, spectrum: np.ndarray, freqs: np.ndarray
    ) -> float:
        return float(freqs[np.argmax(spectrum)])

    def _estimate_snr(
        self, audio: np.ndarray, percentile: float = 10
    ) -> float:
        """Min-statistics SNR estimate (same algorithm as original)."""
        frame_rms = [
            self._rms(audio[i : i + self.FRAME_SIZE])
            for i in range(0, len(audio) - self.FRAME_SIZE, self.HOP_SIZE)
        ]
        if not frame_rms:
            return 0.0
        noise_floor = float(np.percentile(frame_rms, percentile)) + 1e-9
        signal_peak = float(np.percentile(frame_rms, 90))         + 1e-9
        snr         = 20 * np.log10(signal_peak / noise_floor)
        return float(np.clip(snr, -20, 60))
