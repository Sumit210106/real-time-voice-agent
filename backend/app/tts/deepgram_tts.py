

import httpx
import os
import logging

logger = logging.getLogger(__name__)

class DeepgramTTS:
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set")
        self.client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        self.url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=16000"
        
    async def generate_audio(self, text: str) -> bytes:
        """
        Generate audio from text using Deepgram TTS
        Returns: Audio bytes (MP3 or WAV format)
        """
        if not text.strip():
            return b""
        try:
            
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "text": text
            }

            response = await self.client.post(
                self.url, 
                headers=headers, 
                json=payload
            )
            response.raise_for_status()
            
            return response.content
            
        except Exception as e:
            logger.error(f"TTS Error: {e}")
            return b""