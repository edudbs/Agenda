import re
from datetime import datetime
from typing import Dict


TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def normalize_local_datetime(value: str) -> str:
    value = value.strip()

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value

    hour = parsed.hour
    minute = parsed.minute
    second = parsed.second

    if hour > 23:
        hour = hour % 24

    normalized = parsed.replace(
        hour=hour,
        minute=minute,
        second=second,
        microsecond=0,
    )

    return normalized.isoformat(timespec="seconds")


def coerce_calendar_args(function_name: str, args: Dict) -> Dict:
    if function_name not in [
        "add_calendar_event",
        "modify_calendar_event",
    ]:
        return args

    corrected = dict(args)

    for field in ["start_datetime", "end_datetime"]:
        value = corrected.get(field)
        if isinstance(value, str):
            corrected[field] = normalize_local_datetime(value)

    return corrected
