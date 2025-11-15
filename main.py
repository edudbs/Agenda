import os
import json
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import openai
import requests

from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI(title="Agente de Planejamento - FastAPI (Service Account)")

# --- Configuration via environment variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # paste the service account JSON here
# Optionally the calendar id (your email). If empty, will try 'primary' (may refer to service account calendar).
CALENDAR_ID = os.getenv("CALENDAR_ID", None)

if not OPENAI_API_KEY:
    # Service starts but calendar endpoints will raise helpful errors until configured
    app.state.openai_configured = False
else:
    app.state.openai_configured = True
    openai.api_key = OPENAI_API_KEY

if not GOOGLE_CREDENTIALS_JSON:
    app.state.calendar_configured = False
else:
    app.state.calendar_configured = True

# --- Google Calendar helper ---
def get_calendar_service():
    if not app.state.calendar_configured:
        raise HTTPException(status_code=500, detail="GOOGLE_CREDENTIALS_JSON not set in environment.")
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid GOOGLE_CREDENTIALS_JSON: {e}")
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/calendar"]
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return service

# --- Utilities ---
def iso_utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def parse_datetime(dt_str: str) -> datetime:
    # Accept ISO with or without Z; also accept date-only YYYY-MM-DD
    try:
        if dt_str.endswith("Z"):
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return datetime.fromisoformat(dt_str)
    except Exception:
        # try date-only
        return datetime.fromisoformat(dt_str + "T00:00:00+00:00")

# --- Models ---
class CreateEventRequest(BaseModel):
    summary: str
    start: str  # ISO datetime or YYYY-MM-DD
    end: str
    description: Optional[str] = None
    attendees: Optional[List[str]] = None

class PlanRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD
    tasks: Optional[List[str]] = None

# --- Endpoints ---
@app.get("/ping")
def ping():
    return {"status": "ok", "calendar_configured": app.state.calendar_configured, "openai_configured": app.state.openai_configured}

@app.get("/events")
def list_events(date: Optional[str] = None, max_results: int = 50):
    """List events for a given date (YYYY-MM-DD). If date omitted, list next upcoming events."""
    if not app.state.calendar_configured:
        raise HTTPException(status_code=400, detail="Calendar not configured (set GOOGLE_CREDENTIALS_JSON).")

    service = get_calendar_service()
    calendar_id = CALENDAR_ID or "primary"

    if date:
        try:
            d = datetime.fromisoformat(date)
        except Exception:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        start_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)
        timeMin = start_dt.isoformat().replace("+00:00", "Z")
        timeMax = end_dt.isoformat().replace("+00:00", "Z")
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=timeMin,
            timeMax=timeMax,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
    else:
        timeMin = iso_utc_now()
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=timeMin,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

    items = events_result.get("items", [])
    parsed = []
    for e in items:
        parsed.append({
            "id": e.get("id"),
            "summary": e.get("summary"),
            "start": e.get("start"),
            "end": e.get("end"),
            "status": e.get("status"),
            "htmlLink": e.get("htmlLink")
        })
    return {"count": len(parsed), "events": parsed}

@app.post("/events")
def create_event(req: CreateEventRequest):
    if not app.state.calendar_configured:
        raise HTTPException(status_code=400, detail="Calendar not configured (set GOOGLE_CREDENTIALS_JSON).")
    service = get_calendar_service()
    calendar_id = CALENDAR_ID or "primary"

    def to_event_dt(s: str):
        # If date-only, use 'date', else 'dateTime'
        try:
            datetime.fromisoformat(s)
            # contains time
            if s.endswith("Z"):
                return {"dateTime": s}
            return {"dateTime": s}
        except Exception:
            # date-only
            return {"date": s}

    event_body = {
        "summary": req.summary,
        "description": req.description or "",
        "start": to_event_dt(req.start),
        "end": to_event_dt(req.end),
    }
    if req.attendees:
        event_body["attendees"] = [{"email": a} for a in req.attendees]

    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return {"created": True, "id": created.get("id"), "htmlLink": created.get("htmlLink")}

@app.get("/suggest")
def suggest_free_slot(duration_min: int = 60):
    if not app.state.calendar_configured:
        raise HTTPException(status_code=400, detail="Calendar not configured (set GOOGLE_CREDENTIALS_JSON).")
    service = get_calendar_service()
    calendar_id = CALENDAR_ID or "primary"
    now = datetime.now(timezone.utc)
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=now.isoformat().replace("+00:00","Z"),
        maxResults=250,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])

    # Build timeline
    free_start = now
    for e in events:
        start_raw = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        end_raw = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date")
        try:
            start_dt = parse_datetime(start_raw)
            end_dt = parse_datetime(end_raw)
        except Exception:
            continue
        # if there's a gap big enough between free_start and start_dt
        if (start_dt - free_start).total_seconds() >= duration_min * 60:
            return {"start": free_start.isoformat(), "end": (free_start + timedelta(minutes=duration_min)).isoformat()}
        # move free_start forward if event ends later
        if end_dt > free_start:
            free_start = end_dt
    # nothing found in future events — suggest starting now
    return {"start": now.isoformat(), "end": (now + timedelta(minutes=duration_min)).isoformat()}

@app.post("/plan")
def plan_day(req: PlanRequest = Body(...)):
    if not app.state.calendar_configured:
        raise HTTPException(status_code=400, detail="Calendar not configured (set GOOGLE_CREDENTIALS_JSON).")
    if not app.state.openai_configured:
        raise HTTPException(status_code=400, detail="OpenAI not configured (set OPENAI_API_KEY).")

    # determine date
    if req.date:
        try:
            d = datetime.fromisoformat(req.date)
        except Exception:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    else:
        d = datetime.now(timezone.utc)

    service = get_calendar_service()
    calendar_id = CALENDAR_ID or "primary"
    # fetch events for day
    start_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start_dt.isoformat().replace('+00:00','Z'),
        timeMax=end_dt.isoformat().replace('+00:00','Z'),
        maxResults=250,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get("items", [])

    # build prompt
    event_lines = "\n".join([f"- {e.get('start')} → {e.get('summary')}" for e in events]) or "Nenhum evento."
    tasks_section = ""
    if req.tasks:
        tasks_section = "\nTarefas pendentes:\n" + "\n".join(f"- {t}" for t in req.tasks)
    prompt = f"""Você é um assistente organizacional. Hoje é {start_dt.date().isoformat()}.
Eventos do meu Google Calendar para hoje:
{event_lines}
{tasks_section}

Com base nisso, proponha um plano otimizado do dia com blocos de tempo (horários), prioridades e uma sugestão do que adiar se necessário. Seja prático e entregue no formato JSON com campos: morning, afternoon, evening, notes.

Entregue apenas JSON."""

    # call OpenAI
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[
            {"role":"system","content":"Você é um assistente prático de planejamento diário."},
            {"role":"user","content":prompt}
        ],
        temperature=0.2,
        max_tokens=700
    )
    text = resp["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"raw": text}
    return {"date": start_dt.date().isoformat(), "events_count": len(events), "plan": parsed}

# Run with: uvicorn main:app --host 0.0.0.0 --port $PORT
