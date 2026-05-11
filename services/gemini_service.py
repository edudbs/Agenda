import json
import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException
from google import genai
from google.genai.errors import APIError
from google.genai.types import Content, Part

from config import GEMINI_API_KEY, GEMINI_MODEL, USER_TIMEZONE


def get_gemini_client():
    if not GEMINI_API_KEY:
        return None
    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Erro Gemini Client: {e}")
        return None


def build_system_instruction() -> str:
    now_utc = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return (
        f"Você é um planejador de agenda inteligente, prático e consultivo. "
        f"A data e hora atual em UTC são: {now_utc}. "
        f"O fuso horário local do usuário é: {USER_TIMEZONE}. "
        "Você pode listar, criar, modificar e excluir eventos do Google Calendar quando necessário. "
        "Sempre que o usuário pedir agenda, compromissos, horários livres ou planejamento do dia, consulte a agenda primeiro. "
        "Para listar eventos, use datas em UTC com sufixo Z. "
        "Para criar ou modificar eventos, use data/hora local sem sufixo Z e timezone America/Sao_Paulo. "
        "Para excluir ou modificar eventos, você precisa do event_id; se não souber, liste os eventos relevantes antes. "
        "Se houver ambiguidade, pergunte antes de alterar ou excluir. "
        "Responda em português do Brasil, com listas curtas e objetivas."
    )


def parse_history(history: Optional[str], query: str) -> List[Content]:
    parts: List[Content] = []
    if history and history != "null":
        try:
            history_data = json.loads(history)
            for turn in history_data:
                if "role" in turn and "text" in turn:
                    role = "model" if turn["role"] in ["assistant", "model"] else "user"
                    parts.append(Content(role=role, parts=[Part(text=turn["text"])]))
        except json.JSONDecodeError:
            print("Histórico JSON inválido.")

    parts.append(Content(role="user", parts=[Part(text=query)]))
    return parts


def generate_agent_answer(
    query: str,
    history: Optional[str],
    tools: List,
    tool_handlers: Dict,
) -> Dict:
    client = get_gemini_client()
    if not client:
        raise HTTPException(status_code=500, detail="Gemini não configurado. Verifique GEMINI_API_KEY.")

    full_conversation_parts = parse_history(history, query)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_conversation_parts,
            config=genai.types.GenerateContentConfig(
                system_instruction=build_system_instruction(),
                tools=tools,
            ),
        )

        if not response.function_calls:
            return {"answer": response.text or "Sem resposta do modelo.", "function_used": None}

        tool_call = response.function_calls[0]
        function_name = str(tool_call.name)
        args = dict(tool_call.args)

        handler = tool_handlers.get(function_name)
        if handler:
            tool_output = handler(**args)
        else:
            tool_output = {"error": f"Função desconhecida: {function_name}"}

        second_contents = full_conversation_parts[:]
        second_contents.append(response.candidates[0].content)
        second_contents.append(
            Content(
                role="tool",
                parts=[Part.from_function_response(name=tool_call.name, response=tool_output)],
            )
        )

        second_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=second_contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=build_system_instruction(),
                tools=tools,
            ),
        )

        return {"answer": second_response.text or str(tool_output), "function_used": function_name}

    except APIError as e:
        raise HTTPException(status_code=500, detail=f"Erro na API do Gemini: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno do agente: {e}")
