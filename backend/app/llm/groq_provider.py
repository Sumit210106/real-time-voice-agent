import os
import logging
from typing import List, Dict
from dotenv import load_dotenv
from app.sessions import get_session
from groq import AsyncGroq
import re
from .tools import search_web, TAVILY_TOOL_DEFINITION

logger = logging.getLogger(__name__)
load_dotenv()

class GroqLLM:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.error("GROQ_API_KEY is missing from environment.")
            raise ValueError("Missing Groq API Key")
        
        self.client = AsyncGroq(api_key=self.api_key)


    def _get_history(self, session_id: str) -> List[Dict[str, str]]:
        if session_id not in self.sessions:
            self.sessions[session_id] = [{"role": "system", "content": self.system_prompt}]
        return self.sessions[session_id]

    async def get_response(self, text: str, language: str, session_id: str = None):
        """
        Generates a conversational response based on history.
        """
        if not text:
            return ""
        session = get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found.")
            return "I'm sorry, I couldn't find your session."
        try:
            messages = [{"role": "system", "content": session.system_prompt}]
            messages.extend(session.history[-10:])
            messages.append({"role": "user", "content": text})
            
            completion = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                tools=[TAVILY_TOOL_DEFINITION],
                tool_choice="auto",
                max_tokens=300, 
                temperature=0.7,
                top_p=1,
                stream=False 
            )

            response_text = completion.choices[0].message.content
            if response_message.tool_calls:
                messages.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    if tool_call.function.name == "search_web":
                        args = json.loads(tool_call.function.arguments)
                        search_results = await search_web(args['query'])
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": "search_web",
                            "content": search_results
                        })
                final_completion = await self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages
                )
                response_text = final_completion.choices[0].message.content
            else:
                response_text = response_message.content
            session.history.append({"role": "user", "content": text})
            session.history.append({"role": "assistant", "content": response_text})

            if len(session.history) > 20:
                session.history = session.history[-20:]

            return response_text

        except Exception as e:
            logger.error(f"Groq LLM Error: {str(e)}", exc_info=True)
            return "I'm sorry, I'm having trouble thinking right now."
  
    async def get_response_stream(self, text: str, lang: str, session_id: str):
        """
        Streams the response and yields complete sentences while maintaining context.
        """
        session = get_session(session_id)
        if not session:
            yield "Session error."
            return

        messages = [{"role": "system", "content": session.system_prompt}]
        messages.extend(session.history[-10:]) 
        messages.append({"role": "user", "content": text})

        try:

            stream = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=150
            )

            full_response = ""
            buffer = ""
            
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                buffer += token
                full_response += token

                if re.search(r'[.!?](\s|$)', buffer) or '\n' in buffer:
                    parts = re.split(r'([.!?]\s|(?<=[.!?])\n|\n)', buffer, maxsplit=1)
                    if len(parts) > 1:
                        sentence = parts[0] + parts[1]
                        yield sentence.strip()
                        buffer = parts[2] if len(parts) > 2 else ""

            if buffer.strip():
                yield buffer.strip()

            session.history.append({"role": "user", "content": text})
            session.history.append({"role": "assistant", "content": full_response})

        except Exception as e:
            logger.error(f"Groq Stream Error: {e}")
            yield "I encountered an error."