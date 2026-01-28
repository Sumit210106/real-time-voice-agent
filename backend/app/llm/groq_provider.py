import os
import logging
from typing import List, Dict
from dotenv import load_dotenv
from groq import Groq
from app.sessions import get_session

logger = logging.getLogger(__name__)
load_dotenv()

class GroqLLM:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.error("GROQ_API_KEY is missing from environment.")
            raise ValueError("Missing Groq API Key")
        
        self.client = Groq(api_key=self.api_key)


    def _get_history(self, session_id: str) -> List[Dict[str, str]]:
        if session_id not in self.sessions:
            self.sessions[session_id] = [{"role": "system", "content": self.system_prompt}]
        return self.sessions[session_id]

    async def get_response(self, user_text: str, session_id: str) -> str:
        """
        Generates a conversational response based on history.
        """
        if not user_text:
            return ""
        session = get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found.")
            return "I'm sorry, I couldn't find your session."
        try:
            messages = [{"role": "system", "content": session.system_prompt}]
            messages.extend(session.history[-10:])
            messages.append({"role": "user", "content": user_text})
            
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=150, 
                top_p=1,
                stream=False 
            )

            response_text = completion.choices[0].message.content
            session.history.append({"role": "user", "content": user_text})
            session.history.append({"role": "assistant", "content": response_text})

            if len(session.history) > 20:
                session.history = session.history[-20:]

            return response_text

        except Exception as e:
            logger.error(f"Groq LLM Error: {str(e)}", exc_info=True)
            return "I'm sorry, I'm having trouble thinking right now."