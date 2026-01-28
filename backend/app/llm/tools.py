import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from tavily import TavilyClient

logger = logging.getLogger(__name__)


env_path = Path(__file__).parent.parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    logger.warning("⚠️ TAVILY_API_KEY not configured in .env file. Web search will be disabled.")
else:
    logger.info(f"✅ Tavily Key loaded successfully")


TAVILY_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web for real-time news, weather, or facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"]
        }
    }
}

def search_web(query: str) -> str:
    """Search the web using Tavily API and return formatted results."""
    if not TAVILY_API_KEY:
        logger.warning(f"Search requested but TAVILY_API_KEY not configured. Query: {query}")
        return json.dumps({
            "results": [],
            "error": "Web search not configured. Please set TAVILY_API_KEY in .env file.",
            "suggestion": "Get a free API key from https://tavily.com"
        })
    
    try:
        logger.info(f"🔍 Searching Tavily for: {query}")
        client = TavilyClient(api_key=TAVILY_API_KEY)
        
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5
        )
        
        if response and response.get("results"):
            formatted_results = []
            for result in response["results"][:3]:
                formatted_results.append({
                    "title": result.get("title", ""),
                    "content": result.get("content", "")[:500],
                    "url": result.get("url", "")
                })
            
            logger.info(f"✅ Got {len(formatted_results)} search results")
            return json.dumps({
                "results": formatted_results,
                "answer": response.get("answer"),
                "follow_up_questions": response.get("follow_up_questions")
            })
        else:
            return json.dumps({"results": [], "error": "No results found"})
            
    except Exception as e:
        logger.error(f"❌ Search failed: {str(e)}")
        return json.dumps({"results": [], "error": f"Search failed: {str(e)}"})