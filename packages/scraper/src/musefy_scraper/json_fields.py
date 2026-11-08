from datetime import date

from musefy_core.schemas import JSONObject
from pydantic import JsonValue


def obj(value: JsonValue) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def objects(value: JsonValue) -> list[JSONObject]:
    if not isinstance(value, list):
        raise ValueError("Expected array")
    return [obj(item) for item in value]


def text(value: JsonValue) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def integer(value: JsonValue) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def required_id(value: JsonValue) -> int:
    number = integer(value)
    if number is None or number <= 0:
        raise ValueError("Missing positive source ID")
    return number


def number(value: JsonValue) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def day(value: JsonValue) -> date | None:
    raw = text(value)
    return date.fromisoformat(raw[:10]) if raw else None


def names(value: JsonValue) -> list[str]:
    return [name for item in objects(value) if (name := text(item.get("name")))]


def required_text(value: JsonValue) -> str:
    result = text(value)
    if result is None:
        raise ValueError("Missing required text")
    return result
