import json
import os
import asyncio
from websockets.client import connect

class DeepgramStreamingSTT:
    def __init__(self, on_transcript):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.on_transcript = on_transcript
        self.url = (
            "wss://api.deepgram.com/v1/listen?"
            "model=nova-2&encoding=linear16&sample_rate=16000&channels=1"
            "&smart_format=true&endpointing=300"
        )
        self.ws = None

    async def connect(self):
        headers = {"Authorization": f"Token {self.api_key}"}
        self.ws = await connect(self.url, extra_headers=headers)
        asyncio.create_task(self._recv_loop())

    async def _recv_loop(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                if data.get("is_final") and data.get("channel"):
                    transcript = data["channel"]["alternatives"][0]["transcript"]
                    if transcript.strip():
                        await self.on_transcript(transcript)
        except Exception as e:
            print(f"STT Stream Error: {e}")

    async def send_audio(self, chunk: bytes):
        if self.ws:
            await self.ws.send(chunk)