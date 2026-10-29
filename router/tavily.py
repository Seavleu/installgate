"""Tavily search for recent compromise reports (T08). Untrusted, never hard."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from contracts.contracts import Evidence, EvidenceKind, TargetRef

_log = logging.getLogger("installgate.router")

ALLOWED_HOST = "api.tavily.com"
SEARCH_URL = "https://api.tavily.com/search"
TIMEOUT_S = 15.0
DAYS = 30
# Security reports only. A result whose host is outside this list is dropped.
ALLOWED_DOMAINS = ("osv.dev", "nvd.nist.gov", "cisa.gov", "github.blog", "thehackernews.com")


@dataclass(frozen=True)
class TavilyResult:
    evidence: tuple[Evidence, ...]
    calls: int
    failed_closed: bool


def _allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS)


def _name_pattern(name: str) -> re.Pattern[str]:
    """The package name as a whole token. -, _ and . are interchangeable (PEP 503)."""
    parts = [re.escape(part) for part in re.split(r"[-_.]+", name) if part]
    body = r"[-_.]".join(parts)
    return re.compile(rf"(?<![A-Za-z0-9_.\-]){body}(?![A-Za-z0-9_\-]|\.[A-Za-z0-9])", re.IGNORECASE)


def _mentions(target: TargetRef, title: str, snippet: str) -> bool:
    # News search matches loosely; a report that never names the package is not evidence about it.
    pattern = _name_pattern(target.name)
    return bool(pattern.search(title) or pattern.search(snippet))


def _evidence(
    target: TargetRef, number: int, item: dict[str, object], fetched_at: datetime
) -> Evidence | None:
    url = item.get("url")
    title = item.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
        return None
    if not _allowed(url):
        return None
    snippet = item.get("content")
    observed = {
        "title": title.strip()[:200],
        "snippet": snippet.strip()[:400] if isinstance(snippet, str) else "",
    }
    if not _mentions(target, observed["title"], observed["snippet"]):
        return None
    # The page text is data. It cannot choose severity. Untrusted evidence is always soft.
    return Evidence(
        id=f"EV-{number}",
        kind=EvidenceKind.WEB_REPORT,
        source="tavily",
        trust="retrieved_untrusted",
        severity="soft",
        target=target,
        observed=observed,
        source_url=url,
        fetched_at=fetched_at,
        content_hash=Evidence.compute_hash("web_report", target, observed, url),
    )


async def search(target: TargetRef, *, start_id: int = 1) -> TavilyResult:
    """Search allowlisted domains for the last 30 days.

    The query is the package name, never a user URL. A missing key or an HTTP error
    returns no evidence and failed_closed=True. Callers map that to REVIEW.
    """
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key or not 1 <= start_id <= 9999:
        _log.info('{"stage":"tavily","calls":0,"failed_closed":true}')
        return TavilyResult((), 0, True)

    fetched_at = datetime.now(UTC)
    payload: object
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.post(
                SEARCH_URL,
                json={
                    "api_key": key,
                    "query": f"{target.name} package compromise",
                    "topic": "news",
                    "days": DAYS,
                    "max_results": 3,
                    "include_domains": list(ALLOWED_DOMAINS),
                    "search_depth": "basic",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        _log.info('{"stage":"tavily","calls":1,"failed_closed":true}')
        return TavilyResult((), 1, True)

    results = payload.get("results") if isinstance(payload, dict) else None
    found: list[Evidence] = []
    number = start_id
    for item in results if isinstance(results, list) else []:
        if number > 9999 or not isinstance(item, dict):
            break
        evidence = _evidence(target, number, item, fetched_at)
        if evidence is None:
            continue
        found.append(evidence)
        number += 1
    _log.info(
        '{"stage":"tavily","calls":1,"failed_closed":false,"evidence":%d}',
        len(found),
    )
    return TavilyResult(tuple(found), 1, False)
