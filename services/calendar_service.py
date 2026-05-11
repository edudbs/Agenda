import json
import datetime
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials

from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REFRESH_TOKEN,
    GOOGLE_CREDENTIALS,
    SCOPES,
    CALENDAR_ID,
)


def get_calendar_service():
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
