"""Paper cards for arXiv links in watched channels, and the `arxiv <id>` command."""

from __future__ import annotations

import logging
from collections import OrderedDict

from winston import arxiv
from winston.features.base import Feature

log = logging.getLogger(__name__)


class ArxivLinks(Feature):
    name = "arxiv"
    description = (
        "post an arXiv link and I shall swing by with the title, authors, and abstract; "
        "`arxiv <id or link>` works anywhere, no tensor algebra required"
    )
    RECENT_LIMIT = 500

    def __init__(self, settings):
        super().__init__(settings)
        # (stream_id, topic, arxiv_id) already answered; bounded, oldest dropped first.
        self._recent: OrderedDict[tuple[int | None, str | None, str], None] = OrderedDict()

    @staticmethod
    def _command_argument(msg) -> str | None:
        if msg.command is None:
            return None
        head, _, rest = msg.command.strip().partition(" ")
        return rest.strip() if head.lower() == "arxiv" else None

    def wants(self, msg):
        if self._command_argument(msg) is not None:
            return True
        return msg.type == "stream" and msg.stream_name in self.watched_channels and bool(arxiv.extract_ids(msg.content))

    def handle(self, msg, bot):
        argument = self._command_argument(msg)
        if argument is not None:
            ids = arxiv.extract_ids(argument) or arxiv.extract_ids("arXiv:" + argument)
            if not ids:
                bot.reply(msg, "We shall look it up, but I need coordinates: `arxiv <arXiv id or link>`. Even Kepler needed Tycho's data.")
                return
        else:
            ids = [i for i in arxiv.extract_ids(msg.content) if self._first_time(msg, i)]
            if not ids:
                return
        try:
            papers = arxiv.fetch_papers(ids)
        except Exception:  # network trouble must never kill the event loop
            log.exception("arXiv fetch failed for %s", ids)
            return
        for paper in papers:
            bot.reply(msg, arxiv.format_paper(paper))
        found = {paper.id.lower() for paper in papers}
        for missing in (i for i in ids if i.lower() not in found):
            if argument is not None:
                bot.reply(msg, f"I could not find `{missing}`. Either it is behind the event horizon or the id needs a second look.")
            else:
                log.info("arXiv does not know %s (message %s)", missing, msg.id)

    def _first_time(self, msg, arxiv_id: str) -> bool:
        key = (msg.stream_id, msg.topic, arxiv_id)
        if key in self._recent:
            return False
        self._recent[key] = None
        while len(self._recent) > self.RECENT_LIMIT:
            self._recent.popitem(last=False)
        return True

    def remember_own(self, msg):
        for arxiv_id in arxiv.extract_ids(msg.content):
            self._first_time(msg, arxiv_id)
