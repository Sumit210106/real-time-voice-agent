import os
import logging
from tavily import TavilyClient

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

async def search_web(query: str) -> str:
    
    if not tavily:
        logger.error("Tavily API Key is missing. Search skipped.")
        return "Search error: API Key not configured."

    try:
        search_result = tavily.search(
            query=query, 
            search_depth="ultra-fast", 
            max_results=3
        )
        
        results = search_result.get('results', [])
        if not results:
            return "No relevant web results found for this query."
            
        context = "REAL-TIME WEB DATA (Cite these sources in your spoken response):\n"
        for r in results:
            context += f"\n- Source: {r['url']}\n- Excerpt: {r['content']}\n"
        
        return context

    except Exception as e:
        logger.error(f"Tavily Search Error: {str(e)}")
        return "The web search service is currently unavailable. Please answer based on your internal knowledge."

TAVILY_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Use this tool to search the internet for current events, news, weather, or real-time facts that occurred after your training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string", 
                    "description": "A precise search query derived from the user's question."
                }
            },
            "required": ["query"]
        }
    }
}