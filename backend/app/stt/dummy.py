import numpy as np 
import asyncio
from app.stt.base import STTBase

class DummySTT(STTBase):
    async def transcribe(self, audio: np.ndarray) -> str:
        await asyncio.sleep(0.3)
        return "This is a dummy transcription."