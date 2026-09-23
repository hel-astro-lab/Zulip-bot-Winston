"""The feature interface every Winston behaviour implements."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from winston.bot import Message, Winston


class Feature:
    """One unit of Winston behaviour.

    Message-driven features override ``wants``/``handle``. Scheduled features get ``at``
    from their settings and override ``run``. A feature may do both. ``settings`` is the
    feature's ``[features.<name>]`` table from winston.toml.
    """

    name: str = ""
    description: str = ""

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        at = settings.get("at")
        self.at: dt.time | None = dt.time.fromisoformat(at) if at else None
        self.grace = dt.timedelta(minutes=int(settings.get("grace_minutes", 120)))

    @property
    def watched_channels(self) -> list[str]:
        """Channels this feature needs to see every message of; Winston subscribes to them."""
        return list(self.settings.get("channels", []))

    def wants(self, msg: Message) -> bool:
        return False

    def handle(self, msg: Message, bot: Winston) -> None:
        return None

    def remember(self, msg: Message) -> None:
        """Treat whatever this message holds as already handled; used when re-reading history."""
        return None

    def run(self, bot: Winston) -> None:
        raise NotImplementedError(f"{self.name} is not a scheduled feature")
