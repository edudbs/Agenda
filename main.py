import json
import datetime
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials

from config import (
    GEMINI_API_KEY,
    TELEGRAM_TOKEN,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REFRESH_TOKEN,
    GOOGLE_CREDENTIALS,
    SCOPES,
    CALENDAR_ID,
    USER_TIMEZONE,
    GEMINI_MODEL,
)

from auth import check_auth, build_google_flow
from services.gemini_service import generate_agent_answer as generate_gemini_answer
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
# Clientes
# -----------------------------------------------------------------------------

def get_calendar_service():
    """
    Preferência:
    1. OAuth pessoal via GOOGLE_REFRESH_TOKEN.
    2. Fallback opcional via GOOGLE_CREDENTIALS/service account.

    Para agenda pessoal, o recomendado é OAuth + GOOGLE_REFRESH_TOKEN.
    """
    try:
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN:
            creds = Credentials(
                token=None,
                refresh_token=GOOGLE_REFRESH_TOKEN,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                scopes=SCOPES,
            )
            return build("calendar", "v3", credentials=creds)

        if GOOGLE_CREDENTIALS:
            creds_info = json.loads(GOOGLE_CREDENTIALS)
            creds = service_account.Credentials.from_service_account_info(
                creds_info,
                scopes=SCOPES,
            )
            return build("calendar", "v3", credentials=creds)

        return None

    except json.JSONDecodeError:
        print("Erro Calendar: GOOGLE_CREDENTIALS não é um JSON válido.")
        return None
    except Exception as e:
        print(f"Erro Calendar ao construir serviço: {e}")
        return None


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
# Funções de Calendar
# -----------------------------------------------------------------------------

def format_event(e: Dict) -> Dict:
    start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date"))
    end = e.get("end", {}).get("dateTime", e.get("end", {}).get("date"))
    return {
        "summary": e.get("summary", "Sem título"),
        "start": start,
        "end": end,
        "event_id": e.get("id"),
    }


def list_calendar_events(
    max_results: int = 10,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
) -> List[Dict]:
    service = get_calendar_service()
    if not service:
        return [{"error": "Serviço de calendário não configurado. Configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e GOOGLE_REFRESH_TOKEN."}]

    time_min_filter = start_datetime or (datetime.datetime.utcnow().isoformat() + "Z")

    try:
        request = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min_filter,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        if end_datetime:
            request.uri += f"&timeMax={end_datetime}"

        events_result = request.execute()
        events = events_result.get("items", [])
        return [format_event(e) for e in events]

    except Exception as e:
        return [{"error": f"Erro ao listar eventos no Google Calendar: {e}"}]


def add_calendar_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    timezone: str = USER_TIMEZONE,
) -> Dict:
    service = get_calendar_service()
    if not service:
        return {"error": "Serviço de calendário não configurado."}

    event_body = {
        "summary": summary,
        "start": {"dateTime": start_datetime, "timeZone": timezone},
        "end": {"dateTime": end_datetime, "timeZone": timezone},
    }

    try:
        event = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
        return {"created": True, "event_id": event.get("id"), "summary": event.get("summary")}
    except Exception as e:
        return {"error": f"Erro ao criar evento: {e}"}


def delete_calendar_event(event_id: str) -> Dict:
    service = get_calendar_service()
    if not service:
        return {"error": "Serviço de calendário não configurado."}

    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id}
    except Exception as e:
        return {"error": f"Erro ao excluir evento {event_id}: {e}"}


def modify_calendar_event(
    event_id: str,
    summary: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    timezone: str = USER_TIMEZONE,
) -> Dict:
    service = get_calendar_service()
    if not service:
        return {"error": "Serviço de calendário não configurado."}

    try:
        existing_event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()

        if summary is not None:
            existing_event["summary"] = summary
        if start_datetime is not None:
            existing_event["start"] = {"dateTime": start_datetime, "timeZone": timezone}
        if end_datetime is not None:
            existing_event["end"] = {"dateTime": end_datetime, "timeZone": timezone}

        updated_event = service.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=existing_event,
        ).execute()

        return {"modified": True, "event_id": event_id, "summary": updated_event.get("summary")}
    except Exception as e:
        return {"error": f"Erro ao modificar evento {event_id}: {e}"}


# -----------------------------------------------------------------------------
# Agente Gemini
# -----------------------------------------------------------------------------

def generate_agent_answer(query: str, history: Optional[str] = None) -> Dict:
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
    return generate_gemini_answer(query, history, tools, tool_handlers)


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
