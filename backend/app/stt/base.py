from abc import ABC, abstractmethod
import numpy as np

class STTBase(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """
        Input:
            audio: np.ndarray (float32, mono)
        Output:
            transcript: str
        """
        pass

