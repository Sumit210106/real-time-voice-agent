import numpy as np

class UtteranceCollector:
    def __init__(self):
        self.buffer = []
        self.active = False
    # process(samples: np.ndarray, vad_event: dict | None) -> np.ndarray | None
    def process(self,samples , vad_event):
        if vad_event == 'speech_start':
            self.buffer = []
            self.active = True
            self.buffer.append(samples)
            return None 
        
        elif vad_event == "speech_continue" and self.active : 
            self.buffer.append(samples)
            return None
        
        elif vad_event == "speech_end" and self.active :
            self.active = False
            self.buffer.append(samples)
            utterance = np.concatenate(self.buffer, axis=0)
            self.buffer = []
            return utterance
        
        else:
            return None