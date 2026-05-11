import datetime
import json
import re
import requests
from typing import Dict, Optional, Tuple

from fastapi import HTTPException

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_APP_NAME,
    USER_TIMEZONE,
)
from services.datetime_service import coerce_calendar_args


def build_system_prompt() -> str:
    now_utc = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    today_local = datetime.datetime.now().date().isoformat()
    return (
        "Você é um planejador de agenda inteligente, prático e consultivo. "
        f"A data local de hoje é: {today_local}. "
        f"A data e hora atual em UTC são: {now_utc}. "
        f"O fuso horário local do usuário é: {USER_TIMEZONE}. "
        "Responda em português do Brasil, com listas curtas e objetivas. "
        "Considere memórias relevantes do usuário quando presentes no contexto. "
        "Você pode consultar, criar, modificar e excluir eventos do Google Calendar usando as ferramentas disponíveis. "
        "Sempre que o usuário pedir agenda, compromissos, horários livres ou planejamento do dia, consulte a agenda primeiro. "
        "Para perguntas sobre 'hoje', use a data local informada acima. "
        "Para listar eventos, use datas em UTC com sufixo Z. "
        "Para criar ou modificar eventos, use data/hora local no formato ISO, sem sufixo Z. "
        "NUNCA converta automaticamente horários da manhã para tarde. "
        "Se o usuário disser 5:00, interprete como 05:00, salvo indicação explícita de tarde/noite. "
        "Se houver ambiguidade, pergunte antes de alterar ou excluir eventos."
    )


OPENROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "Lista eventos do Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 10},
                    "start_datetime": {"type": "string", "description": "Data/hora inicial em UTC com Z, opcional."},
                    "end_datetime": {"type": "string", "description": "Data/hora final em UTC com Z, opcional."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": "Cria um evento no Google Calendar.",
            "parameters": {
                "type": "object",
                "required": ["summary", "start_datetime", "end_datetime"],
                "properties": {
                    "summary": {"type": "string"},
                    "start_datetime": {"type": "string", "description": "Data/hora local ISO, sem Z."},
                    "end_datetime": {"type": "string", "description": "Data/hora local ISO, sem Z."},
                    "timezone": {"type": "string", "default": "America/Sao_Paulo"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Exclui um evento do Google Calendar pelo event_id.",
            "parameters": {
                "type": "object",
                "required": ["event_id"],
                "properties": {
                    "event_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_calendar_event",
            "description": "Modifica um evento existente do Google Calendar.",
            "parameters": {
                "type": "object",
                "required": ["event_id"],
                "properties": {
                    "event_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "start_datetime": {"type": "string", "description": "Data/hora local ISO, sem Z."},
                    "end_datetime": {"type": "string", "description": "Data/hora local ISO, sem Z."},
                    "timezone": {"type": "string", "default": "America/Sao_Paulo"},
                },
            },
        },
    },
]


def build_headers() -> Dict:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL

    if OPENROUTER_APP_NAME:
        headers["X-Title"] = OPENROUTER_APP_NAME

    return headers


def post_chat_completion(payload: Dict) -> Dict:
    response = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=build_headers(),
        json=payload,
        timeout=60,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Erro OpenRouter: {response.text}",
        )

    return response.json()


def parse_text_tool_call(content: str) -> Optional[Tuple[str, Dict]]:
    if not content or "<tool_call>" not in content:
        return None

    function_match = re.search(r"<function=([a-zA-Z0-9_]+)>", content)
    if not function_match:
        return None

    function_name = function_match.group(1)
    args = {}

    for param_name, param_value in re.findall(
        r"<parameter=([a-zA-Z0-9_]+)>\s*(.*?)\s*</parameter>",
        content,
        flags=re.DOTALL,
    ):
        value = param_value.strip()
        if value.isdigit():
            args[param_name] = int(value)
        else:
            args[param_name] = value

    args = coerce_calendar_args(function_name, args)
    return function_name, args


def execute_text_tool_call(content: str, tool_handlers: Optional[Dict]) -> Optional[Dict]:
    parsed = parse_text_tool_call(content)
    if not parsed:
        return None

    function_name, args = parsed
    handler = (tool_handlers or {}).get(function_name)
    if not handler:
        return {
            "answer": f"Função desconhecida: {function_name}",
            "function_used": function_name,
            "provider": "openrouter",
        }

    tool_output = handler(**args)

    return {
        "answer": json.dumps(tool_output, ensure_ascii=False),
        "function_used": function_name,
        "provider": "openrouter",
        "tool_output": tool_output,
    }


def generate_openrouter_answer(
    query: str,
    history: Optional[str] = None,
    tool_handlers: Optional[Dict] = None,
) -> Dict:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY não configurada.")

    messages = [
        {"role": "system", "content": build_system_prompt()},
    ]

    if history and history != "null":
        messages.append({"role": "assistant", "content": history})

    messages.append({"role": "user", "content": query})

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "tools": OPENROUTER_TOOLS,
        "tool_choice": "auto",
    }

    try:
        data = post_chat_completion(payload)
        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        content = message.get("content") or ""

        if not tool_calls:
            text_tool_result = execute_text_tool_call(content, tool_handlers)
            if text_tool_result:
                return text_tool_result

            return {
                "answer": content or "Sem resposta do modelo.",
                "function_used": None,
                "provider": "openrouter",
            }

        tool_call = tool_calls[0]
        function_name = tool_call["function"]["name"]
        raw_args = tool_call["function"].get("arguments") or "{}"
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        args = coerce_calendar_args(function_name, args)

        handler = (tool_handlers or {}).get(function_name)
        if not handler:
            tool_output = {"error": f"Função desconhecida: {function_name}"}
        else:
            tool_output = handler(**args)

        return {
            "answer": json.dumps(tool_output, ensure_ascii=False),
            "function_used": function_name,
            "provider": "openrouter",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro OpenRouter: {e}")
