from typing import Dict, Optional

from config import CALENDAR_ID, USER_TIMEZONE
from services.calendar_service import get_calendar_service


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
