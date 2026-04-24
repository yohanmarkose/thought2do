"""LangChain tools exposed to agent nodes.

Two tools are currently available:

- `resolve_date`: Backed by `parsedatetime`, converts natural-language
  date phrases (e.g. "next Thursday", "end of month", "in 3 days",
  "at 3pm tomorrow") into ISO 8601 strings anchored to a reference moment.

- `web_search`: Backed by DuckDuckGo (`ddgs`), fetches a short list of
  relevant web results the decomposition agent can fold into a task
  description as bullet points (e.g. "add tips for preparing for a
  dentist appointment", "research how to write a cover letter").
"""
import logging
from datetime import datetime, timezone

import parsedatetime
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

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


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web and return a short list of relevant results.

    Use this tool when the user explicitly asks for research, bullet
    points, preparation tips, links, or background information to fold
    into a task's description — e.g. "add bullet points on how to
    prepare for a dentist appointment", "research how to write a cover
    letter", "add some links about keto recipes to the description".

    Do NOT call this tool:
    - When the user did not ask for research / bullets / links.
    - For date/time resolution (use `resolve_date` for that).
    - For sensitive, private, or medical-advice-specific queries where
      the answer could mislead the user.

    Args:
        query: A concise search query (e.g. "how to prepare for dentist
            appointment", "cover letter tips software engineer").
        max_results: Number of results to return, clamped to 1–8.
            Default 5.

    Returns:
        A plain-text block with each result rendered as
        `"N. Title\\n   URL: ...\\n   Summary: ..."`, separated by
        blank lines. If the search yields nothing or errors out, returns
        a string starting with "ERROR:" — in which case do NOT fabricate
        bullet points; write the description from the model's own
        general knowledge and mention that sources were unavailable.
    """
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError as exc:
        logger.warning("web_search: ddgs not installed: %s", exc)
        return "ERROR: web_search unavailable (ddgs not installed)"

    try:
        n = max(1, min(int(max_results or 5), 8))
    except (TypeError, ValueError):
        n = 5

    query = (query or "").strip()
    if not query:
        return "ERROR: web_search requires a non-empty query"

    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=n))
    except Exception as exc:
        logger.warning("web_search: query %r failed: %s", query, exc)
        return f"ERROR: web_search failed: {exc}"

    if not hits:
        return f"ERROR: no results for {query!r}"

    lines: list[str] = []
    for i, hit in enumerate(hits[:n], start=1):
        title = (hit.get("title") or "").strip() or "(untitled)"
        href = (hit.get("href") or hit.get("url") or "").strip()
        body = (hit.get("body") or hit.get("snippet") or "").strip()
        if len(body) > 240:
            body = body[:237].rstrip() + "..."
        lines.append(f"{i}. {title}\n   URL: {href}\n   Summary: {body}")
    return "\n\n".join(lines)
