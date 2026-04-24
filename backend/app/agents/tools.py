"""LangChain tools exposed to agent nodes.

Currently just `resolve_date`, backed by the `parsedatetime` library,
used by the decomposition agent to convert natural-language date
phrases (e.g. "next Thursday", "end of month", "first of next month",
"in 3 days", "at 3pm tomorrow") into ISO 8601 datetime strings
anchored to a given reference moment.
"""
from datetime import datetime, timezone

import parsedatetime
from langchain_core.tools import tool

# parsedatetime's Calendar is thread-safe for parsing and expensive to
# build (it compiles regex tables on init), so instantiate once.
_CALENDAR = parsedatetime.Calendar()


@tool
def resolve_date(phrase: str, anchor_iso: str) -> str:
    """Resolve a natural-language date/time phrase to an ISO 8601 string.

    Use this tool WHENEVER the user refers to a date or time in natural
    language — weekday names ("this Thursday", "next Friday"), relative
    phrases ("in 3 days", "in two weeks", "end of month", "by end of
    day"), ordinals ("first of next month", "the 15th"), or specific
    times without a date ("at 3pm", which will be resolved against the
    anchor). Do NOT use it for timestamps the user already gave in ISO
    form — just echo those.

    Args:
        phrase: The natural-language date phrase to resolve.
        anchor_iso: The reference datetime (ISO 8601) to anchor
            relative phrases against. MUST be the `current_datetime`
            given in the system prompt.

    Returns:
        An ISO 8601 datetime string like "2026-04-30T09:00:00+00:00",
        or a string starting with "ERROR:" if the phrase could not be
        parsed — in which case keep the task but leave deadline null.
    """
    try:
        anchor = datetime.fromisoformat(anchor_iso.replace("Z", "+00:00"))
    except ValueError:
        return f"ERROR: invalid anchor_iso {anchor_iso!r}"

    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)

    # parsedatetime wants a tz-naive source; we feed the anchor as UTC
    # wall-clock and re-attach UTC after parsing.
    source_naive = anchor.astimezone(timezone.utc).replace(tzinfo=None)
    parsed_naive, status = _CALENDAR.parseDT(phrase, sourceTime=source_naive)
    # status: 0=not parsed, 1=date, 2=time, 3=date+time
    if status == 0:
        return f"ERROR: could not parse phrase {phrase!r}"

    result = parsed_naive.replace(tzinfo=timezone.utc)
    return result.isoformat()
