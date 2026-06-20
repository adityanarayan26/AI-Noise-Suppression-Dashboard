import os
import librosa
import numpy as np

class AudioQualityService:
    """
    Service to analyze audio quality metrics including
    - Voice Clarity Score (0-100)
    - Noise Level (0-100, lower is better)
    - Speech Presence Percentage
    - Overall Audio Quality Score (0-100)
    """
    
    @staticmethod
    def analyze_quality(audio_path: str) -> dict:
        """
        Analyzes audio quality metrics for an input audio file.
        
        Args:
            pcm_bytes:       Raw Int16 PCM for the current frame.
            snr_db:          SNR from NoiseSuppressionService.
            clarity_score:   0–100 from VoiceClarityService.
            noise_class:     Category string from NoiseClassificationService.
            processing_ms:   Wall-clock processing latency measured externally.

        Returns full metrics dict matching the dashboard contract.
        """
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0 #Converts bytes into audio amplitudes.
        rms = float(np.sqrt(np.mean(samples ** 2))) # Measures audio loudness.

        # --- Speech presence detection ---
        #speech_present = self._detect_speech_presence(samples, rms)

        zcr = np.mean(np.abs(np.diff(np.sign(samples))))

        speech_present = (
            rms > 0.003
            and speech_energy_ratio > 0.35
            and zcr > 0.02
        )

        # --- Noise level (0–100, higher = more noise) ---
        noise_level = self._compute_noise_level(samples, snr_db)

        # --- Noise score (inverse of quality, 0=clean, 100=very noisy) ---
        noise_score = int(np.clip(noise_level, 0, 100))

        # --- Audio quality composite (0–100) ---
        # Weights: SNR contributes 40%, clarity 35%, noise level (inverted) 25%
        snr_norm = np.clip((snr_db + 10) / 50 * 100, 0, 100)   # map -10..40 dB → 0..100
        quality_raw = 0.40 * snr_norm + 0.35 * clarity_score + 0.25 * (100 - noise_level)
        audio_quality = int(np.clip(quality_raw, 0, 100))

        # --- Microphone status ---
        if rms < self.SILENCE_THRESHOLD:
            mic_status = "silent"
        else:
            mic_status = "connected"

        # --- Waveform bars (50 bars for the chart) ---
        waveform_bars = self._compute_waveform_bars(samples, n_bars=50)

        # --- Dynamic alerts ---
        alerts = self._generate_alerts(noise_score, clarity_score, noise_class, speech_present)

        latency = max(int(processing_ms), 1)

        return {
            "microphone_status": mic_status,
            "noise_score": noise_score,
            "voice_clarity": int(np.clip(clarity_score, 0, 100)),
            "latency": latency,
            "audio_quality": audio_quality,
            "noise_class": noise_class,
            "noise_level": round(float(noise_level), 1),
            "speech_presence": speech_present,
            "snr_db": round(snr_db, 1),
            "waveform_bars": waveform_bars,
            "alerts": alerts,
        }

'''
    def _detect_speech_presence(self, samples: np.ndarray, rms: float) -> bool:
        """
        Uses spectral energy in the speech band (300–3400 Hz) vs total energy.
        Returns True if the frame likely contains voiced speech.
        """
        if rms < self.SILENCE_THRESHOLD:
            return False

        n = len(samples)
        spectrum = np.abs(rfft(samples)) ** 2  #How much energy exists at each frequency.
        freq_bins = np.fft.rfftfreq(n, d=1.0 / self.SAMPLE_RATE)

        speech_mask = (freq_bins >= 300) & (freq_bins <= 3400)
        total = np.sum(spectrum) + 1e-10
        speech_energy_ratio = float(np.sum(spectrum[speech_mask]) / total)

        return speech_energy_ratio > 0.35
'''
def _detect_speech_presence(self, samples: np.ndarray, rms: float) -> bool:
    if rms < self.SILENCE_THRESHOLD:
        return False

    n = len(samples)

    spectrum = np.abs(rfft(samples)) ** 2
    freq_bins = np.fft.rfftfreq(
        n,
        d=1.0 / self.SAMPLE_RATE
    )

    speech_mask = (
        (freq_bins >= 300)
        & (freq_bins <= 3400)
    )

    total = np.sum(spectrum) + 1e-10

    speech_energy_ratio = float(
        np.sum(spectrum[speech_mask]) / total
    )

    zcr = np.mean(
        np.abs(
            np.diff(
                np.sign(samples)
            )
        )
    )

    speech_present = (
        rms > self.SILENCE_THRESHOLD
        and speech_energy_ratio > 0.35
        and zcr > 0.02
    )

    return speech_present

    def _compute_noise_level(self, samples: np.ndarray, snr_db: float) -> float:
        """
        Convert SNR dB to a 0–100 noise level score.
        High SNR → low noise level; Low/negative SNR → high noise level.
        """
        # SNR range: assume -10 dB (very noisy) → 40 dB (very clean)
        noise_level = np.clip(100 - (snr_db + 10) / 50 * 100, 0, 100)
        return float(noise_level)

    @staticmethod
    def _compute_waveform_bars(samples: np.ndarray, n_bars: int = 50) -> list:
        """
        Divide samples into n_bars equal segments, compute RMS per segment.
        Returns a list of floats 0–100 representing bar heights.
        """
        if len(samples) == 0:
            return [0.0] * n_bars

        # Pad or trim to be divisible
        '''
        remainder = (len(samples)) % n_bars
        if remainder != 0:
            samples = np.pad(samples, (0, n_bars - remainder))
        '''
        pad_needed = (-len(samples)) % n_bars
        if pad_needed:
            samples = np.pad(samples, (0, pad_needed)) 

        segments = samples.reshape(n_bars, -1)
        rms_per_segment = np.sqrt(np.mean(segments ** 2, axis=1))

        # Scale to 0–100 using the max in this frame
        max_rms = rms_per_segment.max()
        if max_rms < 1e-8:
            return [0.0] * n_bars

        bars = (rms_per_segment / max_rms * 100).tolist()
        return [round(b, 1) for b in bars]

    @staticmethod
    def _generate_alerts(
        noise_score: int,
        clarity_score: int,
        noise_class: str,
        speech_present: bool,
    ) -> list:
        """
        Generate contextual alert messages based on current frame analysis.
        """
        alerts = []
        import datetime
        now = datetime.datetime.now().strftime("%I:%M:%S %p")

        if noise_score > 65:
            alerts.append({"message": f"{noise_class} Detected", "time": now, "level": "warning"})

        if clarity_score < 40 and speech_present:
            alerts.append({"message": "Voice Clarity Degraded", "time": now, "level": "warning"})

        if noise_score > 80:
            alerts.append({"message": "High Noise Level — Suppression Active", "time": now, "level": "critical"})

        if not speech_present and noise_score < 20:
            alerts.append({"message": "Audio Clean — No Speech Detected", "time": now, "level": "info"})

        return alerts
