import os
import logging
import json
import re
from typing import List, Dict, AsyncGenerator
from dotenv import load_dotenv
from groq import AsyncGroq
from app.sessions import get_session
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
        self.model = "llama-3.3-70b-versatile"

    async def get_response_stream(self, text: str, lang: str, session_id: str) -> AsyncGenerator[str, None]:
        """
        Streams response from Groq, handles tool calls with 400-error fallback.
        """
        session = get_session(session_id)
        if not session:
            yield "Session error."
            return

        system_instruction = (
            f"{session.system_prompt}\n\n"
            "TOOL USAGE INSTRUCTIONS:\n"
            "- You have access to a search_web tool for finding real-time information.\n"
            "- Use the search_web tool when the user asks about:\n"
            "  * Current news, events, or weather\n"
            "  * Recent information that changes frequently\n"
            "  * Any topic requiring up-to-date facts\n"
            "- The tool will be invoked automatically - do NOT generate function syntax in text.\n"
            "- If you decide to use a tool, the system will handle it.\n"
            "- If the user asks something you can answer from your knowledge, just answer directly.\n"
            "- Always provide a helpful response, with or without tool results."
        )

        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(session.history[-10:]) 
        messages.append({"role": "user", "content": text})

        response_message = None
        
        try:
            initial_completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[TAVILY_TOOL_DEFINITION],
                tool_choice="auto",
                max_tokens=500,
                temperature=0.3
            )
            response_message = initial_completion.choices[0].message
            logger.info(f"✅ Got initial response - Tool calls: {len(response_message.tool_calls) if response_message.tool_calls else 0}")

        except Exception as e:
            if "tool_use_failed" in str(e) or "400" in str(e):
                logger.warning(f"⚠️ Tool Call Syntax Error. Falling back to direct response.")
                fallback_completion = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7
                )
                response_message = fallback_completion.choices[0].message
            else:
                logger.error(f"💥 Groq Unexpected Error: {e}")
                yield "I'm sorry, I encountered a connection error."
                return

        if response_message.tool_calls:
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "search_web":
                    try:
                        args = json.loads(tool_call.function.arguments)
                        query = args.get('query', '')
                        logger.info(f"🔍 [TOOL USE] Searching for: {query}")
                        
                        # Call search_web synchronously (it's now a regular function)
                        search_results = search_web(query)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": "search_web",
                            "content": search_results
                        })
                    except Exception as tool_err:
                        logger.error(f"Failed to execute search tool: {tool_err}")
                        # Return empty results instead of continuing
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": "search_web",
                            "content": json.dumps({"results": [], "error": str(tool_err)})
                        })

            final_stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7
            )
            async for sentence in self._stream_sentences(final_stream):
                yield sentence

        elif response_message.content:
            content = response_message.content.strip()
            
            # Filter out malformed function syntax if present
            if content and not re.match(r'^\w+\{.*\}$', content):
                sentences = re.split(r'(?<=[.!?])\s+', content)
                for s in sentences:
                    if s.strip():
                        yield s.strip()
            else:
                # If response is just malformed function call, ask for clarification or retry
                logger.warning(f"Filtered malformed function call output: {content}")
                yield "I'm processing that request. Could you please repeat your question?"

        session.history.append({"role": "user", "content": text})
        if response_message and response_message.content:
            session.history.append({"role": "assistant", "content": response_message.content})

    async def _stream_sentences(self, stream):
        """
        Buffers tokens to yield complete sentences for smooth TTS.
        """
        buffer = ""
        async for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            buffer += token

            if re.search(r'[.!?](\s|$)', buffer) or '\n' in buffer:
                parts = re.split(r'([.!?]\s|(?<=[.!?])\n|\n)', buffer, maxsplit=1)
                if len(parts) > 1:
                    sentence = parts[0] + parts[1]
                    yield sentence.strip()
                    buffer = parts[2] if len(parts) > 2 else ""
        
        if buffer.strip():
            yield buffer.strip()