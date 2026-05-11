from typing import Dict, List, Optional

from config import LLM_PROVIDER
from providers.openrouter_provider import generate_openrouter_answer
from services.gemini_service import generate_agent_answer as generate_gemini_answer


def generate_llm_answer(
    query: str,
    history: Optional[str],
    tools: List,
    tool_handlers: Dict,
) -> Dict:
    if LLM_PROVIDER == "openrouter":
        return generate_openrouter_answer(query, history)

    return generate_gemini_answer(query, history, tools, tool_handlers)
