import numpy as np

class VoiceActivityDetector:
    """
    Optimized Voice Activity Detector for low-latency voice interactions.
    
    Key improvements:
    - Faster speech detection (reduced min_speech_frames)
    - Quicker silence detection (reduced hangover_frames)
    - More aggressive thresholds for responsiveness
    - Better noise adaptation
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        low_freq: int = 100,
        high_freq: int = 3500,
        noise_alpha: float = 0.95,  # Faster noise adaptation (was 0.98)
        threshold_multiplier: float = 2.0,  # More sensitive (was 2.5)
        min_speech_frames: int = 2,  # Faster speech detection (was 3)
        hangover_frames: int = 5,  # Quicker silence detection (was 8)
    ):
        """
        Initialize VAD with optimized parameters for low latency.
        
        Args:
            sample_rate: Audio sample rate in Hz
            low_freq: Lower frequency bound for speech band
            high_freq: Upper frequency bound for speech band
            noise_alpha: Noise floor adaptation rate (0.95 = faster adaptation)
            threshold_multiplier: Energy threshold above noise floor (2.0 = more sensitive)
            min_speech_frames: Frames needed to trigger speech (2 = ~40ms at 50fps)
            hangover_frames: Frames of silence before ending speech (5 = ~100ms)
        """
        self.sample_rate = sample_rate
        self.low_freq = low_freq
        self.high_freq = high_freq

        # Noise floor tracking
        self.noise_floor = 0.005  # Lower initial noise floor (was 0.008)
        self.noise_alpha = noise_alpha
        self.threshold_multiplier = threshold_multiplier

        # Speech detection state
        self.speech_frames = 0
        self.silence_frames = 0
        self.min_speech_frames = min_speech_frames
        self.hangover_frames = hangover_frames

        self.in_speech = False
        
        # Energy history for smoother detection
        self.energy_history = []
        self.history_size = 3  # Keep last 3 energy values

    def is_speech(self, samples: np.ndarray) -> bool:
        """
        Detect if audio samples contain speech.
        
        Returns:
            True if speech is detected, False otherwise
        """
        # Calculate band-limited energy
        energy = self._band_limited_rms(samples)
        
        # Update energy history
        self.energy_history.append(energy)
        if len(self.energy_history) > self.history_size:
            self.energy_history.pop(0)
        
        # Use smoothed energy for more stable detection
        smoothed_energy = np.mean(self.energy_history) if self.energy_history else energy

        # Update noise floor only during silence
        # This prevents speech from raising the noise floor
        if not self.in_speech:
            self.noise_floor = (
                self.noise_alpha * self.noise_floor
                + (1 - self.noise_alpha) * energy
            )

        # Dynamic threshold based on noise floor
        # Minimum threshold prevents false positives in very quiet environments
        threshold = max(
            0.008,  # Minimum threshold (was 0.01)
            self.noise_floor * self.threshold_multiplier
        )

        # Detect if current energy is above threshold
        loud = smoothed_energy > threshold

        if loud:
            # Increment speech frame counter
            self.speech_frames += 1
            self.silence_frames = 0

            # Transition to speech state after minimum frames
            if self.speech_frames >= self.min_speech_frames:
                if not self.in_speech:
                    # Log speech start for debugging
                    # print(f"🎤 Speech started - Energy: {smoothed_energy:.4f}, Threshold: {threshold:.4f}")
                    pass
                self.in_speech = True

        else:
            # Increment silence frame counter
            self.silence_frames += 1
            self.speech_frames = 0

            # Transition to silence state after hangover period
            if self.silence_frames >= self.hangover_frames:
                if self.in_speech:
                    # Log speech end for debugging
                    # print(f"🔇 Speech ended - Silence frames: {self.silence_frames}")
                    pass
                self.in_speech = False

        return self.in_speech

    def _band_limited_rms(self, samples: np.ndarray) -> float:
        """
        Calculate RMS energy in the speech frequency band.
        
        Uses FFT to isolate speech frequencies (100-3500 Hz) which:
        - Reduces sensitivity to low-frequency noise (rumble, AC hum)
        - Reduces sensitivity to high-frequency noise (hiss, keyboard)
        - Focuses on human voice characteristics
        
        Args:
            samples: Audio samples as numpy array
            
        Returns:
            RMS energy in the speech band
        """
        if len(samples) == 0:
            return 0.0

        # Compute FFT
        fft = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(len(samples), d=1.0 / self.sample_rate)

        # Create frequency band mask
        band_mask = (freqs >= self.low_freq) & (freqs <= self.high_freq)
        band_fft = fft[band_mask]

        if band_fft.size == 0:
            return 0.0

        # Calculate power and RMS
        power = np.abs(band_fft) ** 2
        rms = float(np.sqrt(np.mean(power)))
        
        return rms

    def reset(self):
        """Reset VAD state (useful between sessions)"""
        self.noise_floor = 0.005
        self.speech_frames = 0
        self.silence_frames = 0
        self.in_speech = False
        self.energy_history = []

    def get_stats(self) -> dict:
        """Get current VAD statistics for debugging"""
        return {
            "in_speech": self.in_speech,
            "speech_frames": self.speech_frames,
            "silence_frames": self.silence_frames,
            "noise_floor": self.noise_floor,
            "threshold": max(0.008, self.noise_floor * self.threshold_multiplier)
        }