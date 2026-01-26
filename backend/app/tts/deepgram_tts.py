

import httpx
import os
import logging

logger = logging.getLogger(__name__)

class DeepgramTTS:
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set")

    async def generate_audio(self, text: str) -> bytes:
        """
        Generate audio from text using Deepgram TTS
        Returns: Audio bytes (MP3 or WAV format)
        """
        try:
            url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en"
            
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "text": text
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                audio_bytes = response.content
                logger.info(f"TTS generated {len(audio_bytes)} bytes")
                return audio_bytes
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Deepgram TTS API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"Deepgram TTS failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Deepgram TTS error: {e}")
            raise RuntimeError(f"Deepgram TTS failed: {e}")