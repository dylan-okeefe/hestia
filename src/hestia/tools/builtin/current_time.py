"""Current time tool."""

from datetime import datetime
from zoneinfo import ZoneInfo

from hestia.tools.metadata import tool


@tool(
    name="current_time",
    public_description="Get the current date and time, optionally in a specific timezone.",
    parameters_schema={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone, e.g. 'America/New_York'. Defaults to UTC.",
            }
        },
    },
    max_inline_chars=200,
    tags=["utility"],
    capabilities=[],
)
async def current_time(timezone: str = "UTC") -> str:
    """Get the current date and time."""
    try:
        tz = ZoneInfo(timezone)
    except (KeyError, ValueError):
        return f"Unknown timezone: {timezone!r}. Use an IANA name like 'UTC' or 'America/New_York'."
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")
