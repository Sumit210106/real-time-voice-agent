import numpy as np
import time

class UtteranceCollector:

    def __init__(
        self,
        silence_timeout: float = 1.2,
        min_utterance_sec: float = 0.2,
        early_trigger_sec: float = 0.15,
    ):
        self.buffer = []
        self.active = False
        self.last_speech_time = None
        self.start_time = None
        self.partial_fired = False

        self.silence_timeout = silence_timeout
        self.min_utterance_sec = min_utterance_sec
        self.early_trigger_sec = early_trigger_sec

    def process(self, samples: np.ndarray, is_speech: bool, frame_duration: float):
        now = time.perf_counter()

        # ---------------- SPEECH ----------------
        if is_speech:
            if not self.active:
                self.active = True
                self.buffer = []
                self.start_time = now
                self.partial_fired = False

            self.buffer.append(samples)
            self.last_speech_time = now

            elapsed = now - self.start_time

            # 🔥 EARLY INTENT SIGNAL
            if (
                not self.partial_fired
                and elapsed >= self.early_trigger_sec
            ):
                self.partial_fired = True
                return "EARLY"

            return None

        # ---------------- SILENCE ----------------
        if self.active and self.last_speech_time:
            silence_duration = now - self.last_speech_time

            if silence_duration >= self.silence_timeout:
                utterance = np.concatenate(self.buffer, axis=0)
                self.buffer = []
                self.active = False
                self.last_speech_time = None
                self.start_time = None
                self.partial_fired = False

                utterance_duration = len(utterance) / 16000.0
                if utterance_duration >= self.min_utterance_sec:
                    return utterance

        return None