import numpy as np

class VoiceActivityDetector:
    def __init__(self):
        self.state = "silence"
        self.noise_floor = 0.01
        # speech if rms > noise_floor * 3
        self.threshold_multiplier = 3.0
        
        # hangover logic
        self.silent_frames = 0
        self.max_silent_frames = 5
        
        self.noise_alpha = 0.95
        
        
    def process(self, samples: np.ndarray) -> dict | None:
        '''
            {"event": "speech_start"}
            {"event": "speech_continue"}
            {"event": "speech_end"}
            None
        '''
        
        rms = np.sqrt(np.mean(samples ** 2))
        if self.state == "silence" :
            self.noise_floor = (
                self.noise_alpha * self.noise_floor + (1 - self.noise_alpha) * rms
            )
        threshold = max(0.01, self.noise_floor * self.threshold_multiplier)
        speech_detected = rms > threshold
        if self.state == "silence":
            if speech_detected :
                self.state = "speech"
                self.silent_frames = 0
                return {"event": "speech_start"}
            return None
        else:   #speech
            if speech_detected:
                self.silent_frames = 0
                return {"event":"speech_continue"}
            
            self.silent_frames += 1
            if self.silent_frames >= self.max_silent_frames:
                self.state = "silence"
                self.silent_frames = 0
                return {"event":"speech_end"}
            return None 







