"""Daily arXiv digest: the day's listings filtered by the group's author list."""

from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from winston import arxiv
from winston.features.base import Feature

log = logging.getLogger(__name__)

POSTED_LIMIT = 2000
DEFAULT_HEADER = "**arXiv {categories}, {date}** — {papers} by people on the list"

# TeX letter commands that stand for a letter; accent commands (\v \c \u \H ...) map to nothing.
_TEX_LETTERS = {"ss": "ss", "ae": "ae", "oe": "oe", "aa": "a", "o": "o", "l": "l", "i": "i", "j": "j",
                "AE": "AE", "OE": "OE", "AA": "A", "O": "O", "L": "L"}
_FOLD = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae",
                       "Æ": "AE", "œ": "oe", "Œ": "OE", "þ": "th", "ð": "d"})
_PARTICLES = {"da", "das", "de", "del", "della", "der", "di", "do", "dos", "du", "la", "le", "van", "von", "y"}


def tex_to_text(name: str) -> str:
    """Strip TeX accent markup: ``L\\'opez`` -> ``Lopez``, ``\\v{Z}eljko`` -> ``Zeljko``."""
    name = re.sub(r"\\([a-zA-Z]{1,2})\b\s*", lambda m: _TEX_LETTERS.get(m.group(1), ""), name)
    name = re.sub(r"\\[^a-zA-Z\s]", "", name)
    return name.replace("{", "").replace("}", "")


def normalize(name: str) -> str:
    """ASCII, lowercase, no periods, single spaces: the form names are compared in."""
    text = re.sub(r"\([^)]*\)", " ", tex_to_text(name))  # "(DES Collaboration)"
    text = unicodedata.normalize("NFKD", text.translate(_FOLD))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.replace(".", " ").lower().split())


@dataclass(frozen=True)
class NameKey:
    surname: str
    given: tuple[str, ...]  # normalised given names or initials, in order; empty when only a surname is known


def name_key(name: str) -> NameKey | None:
    """Surname and given names of ``Given Surname``, ``G. Surname``, ``Surname, Given`` or ``Surname``."""
    text = normalize(name)
    if "," in text:
        surname, given = (part.strip() for part in text.split(",", 1))
    else:
        parts = text.split()
        if not parts:
            return None
        surname, given = parts[-1], " ".join(parts[:-1])
    surname = surname.split()[-1] if surname.split() else ""
    if not surname:
        return None
    return NameKey(surname, tuple(token for token in given.split() if token[0].isalpha()))


def abbreviate(name: str) -> str:
    """``Joonas Nättilä`` -> ``J. Nättilä``; particles and the surname are kept: ``J. de la Cruz Rodríguez``."""
    parts = name.split()
    if len(parts) < 2:
        return name
    cut = next((i for i, p in enumerate(parts[:-1]) if p.lower() in _PARTICLES), len(parts) - 1)
    if 2 <= cut < len(parts) - 1 and len(parts[cut - 1]) > 2 and not parts[cut - 1].endswith("."):
        cut -= 1  # "Victor R. Soares da Silva": the word before the particle is part of the surname
    initials = [p[0] + "." for p in parts[:cut] if p[0].isalpha()]
    return " ".join(initials + parts[cut:])


class AuthorList:
    """The group's names to watch for, one per line, ``#`` comments allowed.

    An entry matches an author with the same surname when the entry gives no first name, or
    when the entry's first given name is one of the author's given names ("Miller, Coleman"
    matches "M. Coleman Miller" but "Chen, Alexander Y." does not match "Y. Chen"). An initial,
    on either side, matches a given name by its first letter, so "Kunz, M." and "M. Kunz" match
    anything plausible while "Kunz, Matthew" rejects "Martin Kunz".
    """

    def __init__(self, entries: list[tuple[str, NameKey]]):
        self.entries = entries

    @classmethod
    def parse(cls, text: str) -> AuthorList:
        entries = []
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            key = name_key(line) if line else None
            if key is not None:
                entries.append((line, key))
        return cls(entries)

    @classmethod
    def load(cls, path: Path) -> AuthorList:
        return cls.parse(path.read_text(encoding="utf-8"))

    def matches(self, author: str) -> str | None:
        """The list entry the author matches, or None."""
        key = name_key(author)
        if key is None:
            return None
        for text, entry in self.entries:
            if entry.surname == key.surname and given_names_match(entry.given, key.given):
                return text
        return None


def given_names_match(entry: tuple[str, ...], author: tuple[str, ...]) -> bool:
    if not entry:
        return True
    wanted = entry[0]
    if len(wanted) == 1:
        return any(token[0] == wanted for token in author)
    return any(token == wanted or (len(token) == 1 and token == wanted[0]) for token in author)


class Digest(Feature):
    name = "digest"
    description = "every morning I comb the new astro-ph listings for papers and bananas; `digest` asks me to do it right now"

    @property
    def categories(self) -> list[str]:
        return list(self.settings.get("categories", ["astro-ph"]))

    @property
    def announce_types(self) -> set[str]:
        return set(self.settings.get("announce_types", ["new", "cross"]))

    # ----- triggers ----------------------------------------------------------------------

    def run(self, bot):
        self.post_digest(bot)

    def wants(self, msg):
        return msg.command is not None and msg.command.strip().lower() == "digest"

    def handle(self, msg, bot):
        count = self.post_digest(bot)
        if count:
            bot.reply(msg, f"{count} notable paper{'s' if count != 1 else ''}, filed in #**{self.settings['channel']}>{self.settings['topic']}**.")
        else:
            bot.reply(msg, "Nothing to report. Even the arXiv has a rest frame.")

    # ----- the digest ----------------------------------------------------------------------

    def post_digest(self, bot) -> int:
        """Fetch the listings, post the flagged papers, remember what was seen. Returns papers posted."""
        authors = AuthorList.load(bot.config.resolve(self.settings.get("authors", "authors.txt")))
        if not authors.entries:
            log.warning("author list is empty; nothing can be flagged")
        state = bot.feature_state(self.name)
        posted: list[str] = state.setdefault("posted", [])

        day: dt.date | None = None
        listings: dict[str, arxiv.Listing] = {}
        for category in self.categories:
            listing_day, entries = arxiv.fetch_listing(category)
            day = listing_day if day is None else max(day, listing_day)
            for entry in entries:
                listings.setdefault(entry.id, entry)
        fresh = [e for e in listings.values() if e.announce_type in self.announce_types and e.id not in posted]
        hits = [e for e in fresh if any(authors.matches(a) for a in e.authors)]
        log.info("digest %s: %d entries, %d fresh, %d flagged", day, len(listings), len(fresh), len(hits))

        if hits:
            names_by_id = self._clean_names(hits)
            lines = [self._line(e, names_by_id.get(e.id) or tuple(tex_to_text(a) for a in e.authors), authors) for e in hits]
            lines.sort(key=lambda pair: pair[0])
            n = len(hits)
            header = self.settings.get("header", DEFAULT_HEADER).format(
                categories=", ".join(self.categories),
                date=f"{day:%A} {day.day} {day:%B %Y}",
                n=n,
                papers=f"{n} paper{'s' if n != 1 else ''}",
            )
            bot.post(self.settings["channel"], self.settings["topic"], "\n".join([header] + [line for _, line in lines]))

        posted.extend(e.id for e in fresh)
        del posted[:-POSTED_LIMIT]
        bot.save_state()
        return len(hits)

    @staticmethod
    def _clean_names(hits: list[arxiv.Listing]) -> dict[str, tuple[str, ...]]:
        """Author names with proper accents from the arXiv API; empty on failure (feed names are used then)."""
        try:
            return {paper.id: paper.authors for paper in arxiv.fetch_papers([e.id for e in hits])}
        except Exception:
            log.warning("arXiv API unavailable, using feed author names", exc_info=True)
            return {}

    def _line(self, entry: arxiv.Listing, names: tuple[str, ...], authors: AuthorList) -> tuple[str, str]:
        """(sort key, Markdown line) for one flagged paper."""
        matched = [authors.matches(n) is not None for n in names]
        shown = [f"**{abbreviate(n)}**" if hit else abbreviate(n) for n, hit in zip(names, matched)]
        limit = int(self.settings.get("max_listed_authors", 6))
        if len(shown) > limit:
            extra = [s for s, hit in zip(shown[3:], matched[3:]) if hit]
            shown = shown[:3] + (["…"] + extra if extra else []) + ["et al."]
        first_hit = next((name_key(n).surname for n, hit in zip(names, matched) if hit), "")  # type: ignore[union-attr]
        return first_hit, f'- {", ".join(shown)}: "{entry.title}" {entry.abs_url}'
