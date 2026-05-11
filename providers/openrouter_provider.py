import requests
from typing import Dict, Optional

from fastapi import HTTPException

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_APP_NAME,
)


SYSTEM_PROMPT = (
    "Você é um planejador de agenda inteligente, prático e consultivo. "
    "Responda em português do Brasil, com listas curtas e objetivas. "
    "Considere memórias relevantes do usuário quando presentes no contexto."
)


def generate_openrouter_answer(query: str, history: Optional[str] = None) -> Dict:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY não configurada.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    if history and history != "null":
        messages.append({"role": "assistant", "content": history})

    messages.append({"role": "user", "content": query})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL

    if OPENROUTER_APP_NAME:
        headers["X-Title"] = OPENROUTER_APP_NAME

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
    }

    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail=f"Erro OpenRouter: {response.text}",
            )

        data = response.json()
        answer = data["choices"][0]["message"]["content"]

        return {
            "answer": answer,
            "function_used": None,
            "provider": "openrouter",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro OpenRouter: {e}")
