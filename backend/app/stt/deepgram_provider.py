
import httpx
import os

class DeepgramSTT:
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set")
        
        self.client = httpx.AsyncClient(
            timeout=10.0, 
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        self.url = "https://api.deepgram.com/v1/listen"

    async def transcribe(self, wav_bytes: bytes):
        """
        wav_bytes: PCM16 WAV bytes
        returns: (transcript, language)
        """
        try:
            url = "https://api.deepgram.com/v1/listen"
            
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "audio/wav"
            }
            
            params = {
                "model": "nova-2",
                "language": "en",
                "smart_format": "true",
                "punctuate": "true"
            }

            response = await self.client.post(
                    self.url,
                    headers=headers,
                    params=params,
                    content=wav_bytes
                )
            response.raise_for_status()
            
            data = response.json()
            alt = data["results"]["channels"][0]["alternatives"][0]
            transcript = alt.get("transcript", "")
            lang = data.get("metadata", {}).get("detected_language", "en")
            
            return transcript, lang
            
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Deepgram API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Deepgram STT failed: {e}")