"""`secret`: one line from secrets.txt per day, told only in a direct message."""

from __future__ import annotations

import datetime as dt
import logging
import random
from pathlib import Path

from winston.features.base import Feature

log = logging.getLogger(__name__)


def today(tz) -> str:
    return dt.datetime.now(tz).date().isoformat()


def load_secrets(path: Path) -> list[str]:
    """Non-blank, non-comment lines of the secrets file; empty with a warning when the file is missing."""
    if not path.exists():
        log.warning("secrets file %s does not exist", path)
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


class Secret(Feature):
    name = "secret"
    description = "every professor keeps a few; `secret` in a direct message gets you one"

    def wants(self, msg):
        return msg.command is not None and msg.command.strip().lower() == "secret"

    def handle(self, msg, bot):
        if not msg.is_dm:
            bot.reply(msg, "Not here. Secrets travel by direct message only.")
            return
        state = bot.feature_state(self.name)
        day = today(bot.tz)
        if state.get("date") == day:
            bot.reply(msg, "Today's secret has already been told. The universe rations these; come back tomorrow.")
            return
        phrases = load_secrets(bot.config.resolve(self.settings.get("secrets", "secrets.txt")))
        if not phrases:
            bot.reply(msg, "I have no secrets today. Even a professor's drawer runs empty now and then.")
            return
        phrase = random.choice([p for p in phrases if p != state.get("last")] or phrases)
        bot.reply(msg, phrase)
        state.update(date=day, last=phrase, user=msg.sender_id)
        bot.save_state()
