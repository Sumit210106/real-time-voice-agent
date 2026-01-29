import json
import os
import asyncio
import logging
from websockets.client import connect

logger = logging.getLogger(__name__)

class DeepgramStreamingSTT:
    def __init__(self, on_transcript):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.on_transcript = on_transcript
        self.ws = None

        self.url = (
            "wss://api.deepgram.com/v1/listen?"
            "model=nova-2&encoding=linear16&sample_rate=16000&channels=1"
            "&smart_format=true&endpointing=300"
        )

    async def connect(self):
        headers = {"Authorization": f"Token {self.api_key}"}
        self.ws = await connect(self.url, extra_headers=headers)
        asyncio.create_task(self._recv_loop())
        logger.info("✅ Deepgram STT connected")

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
            logger.info("🛑 Deepgram STT disconnected")

    async def send_audio(self, chunk: bytes):
        if self.ws:
            await self.ws.send(chunk)

    async def _recv_loop(self):
        try:
            async for message in self.ws:
                data = json.loads(message)

                # Ignore non-transcript payloads
                if "channel" not in data:
                    continue

                channel = data.get("channel", {})
                alternatives = channel.get("alternatives", [])

                if not alternatives:
                    continue

                transcript = alternatives[0].get("transcript", "").strip()

                if transcript and data.get("is_final"):
                    await self.on_transcript(transcript)

        except Exception as e:
            logger.error(f"STT Stream Error: {e}")
