"""arXiv support: ID extraction from message text, metadata fetch, and the paper card."""

from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"
LISTING_URL = "https://rss.arxiv.org/rss/{category}"
USER_AGENT = "winston-zulip-bot/0.1"
MIN_INTERVAL_S = 3.0  # arXiv asks for a 3 s gap between successive API calls
TIMEOUT_S = 10.0
MAX_AUTHORS = 10

_NEW_ID = r"\d{4}\.\d{4,5}"
_OLD_ID = r"[a-z-]+(?:\.[a-z-]+)?/\d{7}"
_PREFIX = (
    r"(?:https?://)?(?:(?:www|export)\.)?arxiv\.org/(?:abs|pdf|html)/"
    r"|(?:https?://)?ar5iv(?:\.labs)?\.arxiv\.org/(?:abs|html)/"
    r"|arxiv:\s?"
)
# An ID counts only after an arXiv URL or an "arXiv:" prefix; bare numbers never match.
ARXIV_ID_RE = re.compile(rf"(?:{_PREFIX})(?P<id>{_NEW_ID}|{_OLD_ID})(?:v\d+)?", re.IGNORECASE)

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"


@dataclass(frozen=True)
class Paper:
    id: str  # without version, e.g. "2406.01234" or "astro-ph/0601001"
    title: str
    authors: tuple[str, ...]
    abstract: str
    primary_category: str
    published: dt.date

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.id}"


def extract_ids(text: str) -> list[str]:
    """arXiv IDs mentioned in text: version stripped, first-appearance order, no repeats."""
    ids: list[str] = []
    for match in ARXIV_ID_RE.finditer(text):
        arxiv_id = match.group("id")
        if arxiv_id not in ids:
            ids.append(arxiv_id)
    return ids


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_feed(xml_text: str) -> list[Paper]:
    """Papers in an arXiv API Atom feed. Error entries (malformed IDs) are logged and skipped."""
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.iter(f"{_ATOM}entry"):
        entry_id = entry.findtext(f"{_ATOM}id", "")
        if "/api/errors" in entry_id:
            log.warning("arXiv API error entry: %s", entry_id)
            continue
        category = entry.find(f"{_ARXIV}primary_category")
        papers.append(
            Paper(
                id=strip_version(entry_id.rsplit("/abs/", 1)[-1]),
                title=_clean(entry.findtext(f"{_ATOM}title")),
                authors=tuple(_clean(a.findtext(f"{_ATOM}name")) for a in entry.findall(f"{_ATOM}author")),
                abstract=_clean(entry.findtext(f"{_ATOM}summary")),
                primary_category=category.get("term", "") if category is not None else "",
                published=dt.date.fromisoformat(entry.findtext(f"{_ATOM}published", "")[:10]),
            )
        )
    return papers


_throttle_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    with _throttle_lock:
        wait = _last_call + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def fetch_papers(ids: list[str]) -> list[Paper]:
    """Metadata for the given IDs in one API call. IDs arXiv does not know are simply absent."""
    if not ids:
        return []
    _throttle()
    response = requests.get(
        API_URL,
        params={"id_list": ",".join(ids), "max_results": len(ids)},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    return parse_feed(response.text)


def format_paper(paper: Paper) -> str:
    """The paper card in Zulip Markdown: title, link line, authors, abstract in a spoiler."""
    if len(paper.authors) > MAX_AUTHORS:
        authors = ", ".join(paper.authors[:MAX_AUTHORS]) + f", et al. ({len(paper.authors)} authors)"
    else:
        authors = ", ".join(paper.authors)
    return (
        f"**{paper.title}**\n"
        f"[arXiv:{paper.id}]({paper.abs_url}) · {paper.primary_category} · {paper.published.isoformat()}\n"
        f"{authors}\n"
        f"```spoiler Abstract\n{paper.abstract}\n```"
    )


@dataclass(frozen=True)
class Listing:
    """One entry of a daily announcement listing. Author names are as the feed gives them (TeX-encoded)."""

    id: str
    title: str
    authors: tuple[str, ...]
    announce_type: str  # new | cross | replace | replace-cross
    categories: tuple[str, ...]
    abstract: str

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.id}"


def parse_listing(xml_text: str) -> tuple[dt.date, list[Listing]]:
    """Announcement date and entries of an arXiv RSS listing."""
    channel = ET.fromstring(xml_text).find("channel")
    if channel is None:
        raise ValueError("not an RSS feed: no <channel>")
    day = parsedate_to_datetime(channel.findtext("pubDate", "")).date()
    entries: list[Listing] = []
    for item in channel.iter("item"):
        creators = item.findtext(f"{_DC}creator", "")
        entries.append(
            Listing(
                id=strip_version(item.findtext("guid", "").rsplit(":", 1)[-1]),
                title=_clean(item.findtext("title")),
                authors=tuple(a.strip() for a in creators.split(",") if a.strip()),
                announce_type=item.findtext(f"{_ARXIV}announce_type", ""),
                categories=tuple(c.text or "" for c in item.findall("category")),
                abstract=_clean(item.findtext("description", "").split("Abstract:", 1)[-1]),
            )
        )
    return day, entries


def fetch_listing(category: str) -> tuple[dt.date, list[Listing]]:
    """Today's announcement listing for a category such as ``astro-ph`` or ``astro-ph.HE``."""
    response = requests.get(
        LISTING_URL.format(category=category), headers={"User-Agent": USER_AGENT}, timeout=30.0
    )
    response.raise_for_status()
    return parse_listing(response.text)
