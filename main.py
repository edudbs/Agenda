from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from config import (
    GEMINI_API_KEY,
    TELEGRAM_TOKEN,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REFRESH_TOKEN,
    GOOGLE_CREDENTIALS,
    CALENDAR_ID,
    GEMINI_MODEL,
)

from auth import check_auth, build_google_flow
from services.calendar_service import list_calendar_events
from services.calendar_write_service import (
    add_calendar_event,
    delete_calendar_event,
    modify_calendar_event,
)
from services.gemini_service import generate_agent_answer as generate_gemini_answer
from services.memory_service import (
    add_memory,
    build_memory_context,
    extract_explicit_memory,
)
from services.telegram_service import send_telegram_message


# -----------------------------------------------------------------------------
# Inicialização
# -----------------------------------------------------------------------------

app = FastAPI(title="Agente de Planejamento")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# OAuth Google Calendar
# -----------------------------------------------------------------------------

@app.get("/authorize")
def authorize():
    flow = build_google_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(authorization_url)


@app.get("/oauth/callback")
def oauth_callback(code: str):
    flow = build_google_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials

    if not credentials.refresh_token:
        return {
            "status": "autorizado_sem_refresh_token",
            "message": "Google autorizou, mas não retornou refresh_token. Revogue o acesso do app na conta Google e tente /authorize novamente com prompt=consent.",
        }

    return {
        "status": "Google Calendar conectado com sucesso",
        "next_step": "Copie o refresh_token abaixo e salve no Render como GOOGLE_REFRESH_TOKEN. Depois faça Restart Service.",
        "GOOGLE_REFRESH_TOKEN": credentials.refresh_token,
    }


# -----------------------------------------------------------------------------
# Agente Gemini
# -----------------------------------------------------------------------------

def generate_agent_answer(query: str, history: Optional[str] = None) -> Dict:
    explicit_memory = extract_explicit_memory(query)
    if explicit_memory:
        result = add_memory(explicit_memory)
        if "error" in result:
            return {"answer": result["error"], "function_used": "add_memory"}
        return {
            "answer": "Memória salva com sucesso.",
            "function_used": "add_memory",
            "memory": result,
        }

    memory_context = build_memory_context(query)
    enriched_query = query
    if memory_context:
        enriched_query = f"{memory_context}\n\nMensagem atual do usuário:\n{query}"

    tools = [
        list_calendar_events,
        add_calendar_event,
        delete_calendar_event,
        modify_calendar_event,
    ]
    tool_handlers = {
        "list_calendar_events": list_calendar_events,
        "add_calendar_event": add_calendar_event,
        "delete_calendar_event": delete_calendar_event,
        "modify_calendar_event": modify_calendar_event,
    }
    return generate_gemini_answer(enriched_query, history, tools, tool_handlers)


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@app.get("/")
def health_check():
    return {"status": "Serviço ativo", "info": "A API está respondendo"}


@app.get("/ping")
def ping():
    return {
        "status": "ok",
        "calendar_configured": bool((GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN) or GOOGLE_CREDENTIALS),
        "gemini_configured": bool(GEMINI_API_KEY),
        "telegram_configured": bool(TELEGRAM_TOKEN),
        "calendar_id": CALENDAR_ID,
        "model": GEMINI_MODEL,
    }


@app.head("/ping")
def ping_head():
    return {"status": "ok"}


@app.get("/events")
def get_events(token: str, max_results: int = 20):
    check_auth(token)
    result = list_calendar_events(max_results=max_results)
    if result and "error" in result[0]:
        raise HTTPException(status_code=500, detail=result[0]["error"])
    return {"events": result}


@app.post("/add_event")
def create_event(summary: str, start_datetime: str, end_datetime: str, token: str):
    check_auth(token)
    result = add_calendar_event(summary, start_datetime, end_datetime)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.get("/chat")
def chat(query: str, token: str, history: Optional[str] = None):
    check_auth(token)
    return generate_agent_answer(query, history)


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    print("TELEGRAM DATA:", data)

    try:
        message = data.get("message", {}).get("text")
        chat_id = data.get("message", {}).get("chat", {}).get("id")

        if not message or not chat_id:
            return {"status": "ignored", "reason": "sem texto ou chat_id"}

        try:
            result = generate_agent_answer(message)
            reply = result.get("answer", "Sem resposta.")
        except Exception as agent_error:
            print("ERRO AGENTE:", str(agent_error))
            reply = f"Erro ao consultar o agente: {str(agent_error)}"

        return send_telegram_message(chat_id, reply)

    except Exception as e:
        print("ERRO GERAL TELEGRAM:", str(e))
        return {"error": str(e)}
