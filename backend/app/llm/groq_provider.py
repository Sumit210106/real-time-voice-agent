import os
import logging
from typing import List, Dict
from dotenv import load_dotenv
from groq import Groq

logger = logging.getLogger(__name__)
load_dotenv()

class GroqLLM:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.error("GROQ_API_KEY is missing from environment.")
            raise ValueError("Missing Groq API Key")
        
        self.client = Groq(api_key=self.api_key)
        
        self.sessions: Dict[str, List[Dict[str, str]]] = {}
        
        self.system_prompt = (
            "You are a helpful, witty, and concise voice assistant. "
            "Keep responses short (under 2 sentences) to maintain conversation flow. "
            "Avoid using lists, bullet points, or complex punctuation that is hard to read aloud. "
            "Speak naturally, as if you are on a phone call."
        )

    def _get_history(self, session_id: str) -> List[Dict[str, str]]:
        if session_id not in self.sessions:
            self.sessions[session_id] = [{"role": "system", "content": self.system_prompt}]
        return self.sessions[session_id]

    async def get_response(self, user_text: str, language: str, session_id: str) -> str:
        """
        Generates a conversational response based on history.
        """
        if not user_text:
            return ""

        try:
            history = self._get_history(session_id)
            history.append({"role": "user", "content": user_text})
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=history,
                temperature=0.7,
                max_tokens=150, 
                top_p=1,
                stream=False 
            )

            response_text = completion.choices[0].message.content
            history.append({"role": "assistant", "content": response_text})

            if len(history) > 11:
                self.sessions[session_id] = [history[0]] + history[-10:]

            return response_text

        except Exception as e:
            logger.error(f"Groq LLM Error: {str(e)}", exc_info=True)
            return "I'm sorry, I'm having trouble thinking right now."