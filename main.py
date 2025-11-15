import os
import datetime
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI

# Inicializa FastAPI
app = FastAPI()

# CORS (libera acesso ao seu servidor)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Autenticação simples por token
API_TOKEN = os.getenv("API_TOKEN", "changeme")


def check_auth(token):
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# Google Calendar
def get_calendar_service():
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json:
            return None

        creds = service_account.Credentials.from_service_account_info(
            eval(creds_json),
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build("calendar", "v3", credentials=creds)
        return service

    except Exception as e:
        print("Erro Calendar:", e)
        return None


# OpenAI
def get_openai_client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)


# ────────────────────────────────────────────────
# 1) Ping / Status
# ────────────────────────────────────────────────
@app.get("/ping")
def ping():
    return {
        "status": "ok",
        "calendar_configured": bool(os.getenv("GOOGLE_CREDENTIALS")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY"))
    }


# ────────────────────────────────────────────────
# 2) Listar eventos
# ────────────────────────────────────────────────
@app.get("/events")
def list_events(token: str = Header(None)):
    check_auth(token)

    service = get_calendar_service()
    if not service:
        raise HTTPException(status_code=500, detail="Erro ao carregar Google Calendar")

    now = datetime.datetime.utcnow().isoformat() + "Z"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])

    formatted = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date"))
        formatted.append({
            "summary": e.get("summary", "Sem título"),
            "start": start
        })

    return {"events": formatted}


# ────────────────────────────────────────────────
# 3) Criar evento
# ────────────────────────────────────────────────
@app.post("/add_event")
def add_event(summary: str, start: str, end: str, token: str = Header(None)):
    check_auth(token)

    service = get_calendar_service()
    if not service:
        raise HTTPException(status_code=500, detail="Erro Calendar")

    event_body = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"}
    }

    event = service.events().insert(calendarId="primary", body=event_body).execute()

    return {"created": True, "event": event}


# ────────────────────────────────────────────────
# 4) Agente inteligente
# ────────────────────────────────────────────────
@app.get("/chat")
def chat(query: str, token: str = Header(None)):
    check_auth(token)

    service = get_calendar_service()
    if not service:
        raise HTTPException(status_code=500, detail="Erro Calendar")

    # Buscar eventos futuros
    now = datetime.datetime.utcnow().isoformat() + "Z"
    events_result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=15,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    items = events_result.get("items", [])

    event_lines = "\n".join([
        f"- {e.get('start').get('dateTime', e.get('start').get('date'))} → {e.get('summary', 'Sem título')}"
        for e in items
    ]) or "Nenhum evento."

    client = get_openai_client()
    if not client:
        raise HTTPException(status_code=500, detail="Erro OpenAI")

    prompt = f"""
Você é um assistente de organização pessoal. Aqui estão os próximos eventos do usuário:

{event_lines}

Pergunta do usuário:
{query}

Responda com clareza, objetividade e, se necessário, sugira horários livres com base na agenda acima.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    reply = response.output_text

    return {
        "answer": reply,
        "events_used": event_lines
    }
