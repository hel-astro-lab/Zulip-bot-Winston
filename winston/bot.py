"""Winston: Zulip client, event loop, start-up catch-up, scheduler, and feature dispatch."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import zulip

from winston.features import FEATURES, Feature

log = logging.getLogger(__name__)

SCHEDULER_TICK_S = 30
CATCH_UP_BATCH = 200


@dataclass
class Message:
    id: int
    sender_id: int
    sender_email: str
    type: str  # "stream" or "private"
    content: str  # raw Zulip Markdown
    timestamp: int
    stream_id: int | None = None
    stream_name: str | None = None
    topic: str | None = None
    recipient_ids: tuple[int, ...] = ()  # direct-message participants
    is_mentioned: bool = False
    command: str | None = None  # content with Winston's mention removed; only for DMs and mentions

    @property
    def is_dm(self) -> bool:
        return self.type == "private"

    @classmethod
    def from_zulip(cls, m: dict[str, Any], flags: list[str], mention_re: re.Pattern[str]) -> Message:
        msg = cls(
            id=m["id"],
            sender_id=m["sender_id"],
            sender_email=m["sender_email"],
            type=m["type"],
            content=m["content"],
            timestamp=m["timestamp"],
            is_mentioned="mentioned" in flags,
        )
        if msg.type == "stream":
            msg.stream_id = m["stream_id"]
            msg.stream_name = m["display_recipient"]
            msg.topic = m["subject"]
        else:
            msg.recipient_ids = tuple(r["id"] for r in m["display_recipient"])
        if msg.is_dm or msg.is_mentioned:
            msg.command = mention_re.sub("", msg.content).strip()
        return msg


@dataclass
class Config:
    path: Path
    timezone: str = "UTC"
    zuliprc: str | None = None
    state_file: str = "state.json"
    catch_up_hours: float = 24
    features: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Config:
        data = tomllib.loads(path.read_text())
        unknown = set(data) - {"timezone", "zuliprc", "state_file", "catch_up_hours", "features"}
        if unknown:
            raise ValueError(f"{path}: unknown settings {sorted(unknown)}")
        return cls(path=path, **data)

    def resolve(self, relative: str) -> Path:
        return (self.path.parent / Path(relative).expanduser()).resolve()


def is_due(at: dt.time, grace: dt.timedelta, now: dt.datetime, last_fired: str | None) -> bool:
    """True when today's `at` has passed by less than `grace` and nothing fired today."""
    if last_fired == now.date().isoformat():
        return False
    scheduled = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return scheduled <= now < scheduled + grace


class Winston:
    def __init__(self, config: Config, client: Any | None = None) -> None:
        self.config = config
        if client is None:
            zuliprc = str(config.resolve(config.zuliprc)) if config.zuliprc else None
            client = zulip.Client(config_file=zuliprc)
        self.client = client
        profile = self.client.get_profile()
        self.user_id: int = profile["user_id"]
        self.email: str = profile["email"]
        self.name: str = profile["full_name"]
        self._mention_re = re.compile(r"@\*\*" + re.escape(self.name) + r"(?:\|\d+)?\*\*\s*")
        self.tz = ZoneInfo(config.timezone)
        self.features: list[Feature] = [
            cls(config.features.get(cls.name, {}))
            for cls in FEATURES
            if config.features.get(cls.name, {}).get("enabled", True)
        ]
        self.scheduled = [f for f in self.features if f.at is not None]
        self._state_path = config.resolve(config.state_file)
        self._state: dict[str, Any] = self._load_state()
        self._lock = threading.Lock()

    # ----- lifecycle -------------------------------------------------------------------

    @property
    def watched_channels(self) -> list[str]:
        return sorted({channel for feature in self.features for channel in feature.watched_channels})

    def start(self) -> None:
        self._subscribe()
        self._catch_up()
        threading.Thread(target=self._scheduler_loop, name="scheduler", daemon=True).start()
        log.info("%s is listening (features: %s)", self.name, ", ".join(f.name for f in self.features))
        self.client.call_on_each_event(self._on_event, event_types=["message"])

    def _subscribe(self) -> None:
        channels = self.watched_channels
        if not channels:
            return
        result = self.client.add_subscriptions([{"name": channel} for channel in channels])
        if result.get("result") == "success":
            log.info("subscribed to %s", ", ".join(channels))
        else:
            log.error("could not subscribe to %s: %s", channels, result.get("msg"))

    def _on_event(self, event: dict[str, Any]) -> None:
        if event.get("type") != "message":
            return
        try:
            self.dispatch(Message.from_zulip(event["message"], event.get("flags", []), self._mention_re))
        except Exception:  # one bad event must never end the loop
            log.exception("failed to handle event %s", event.get("id"))

    def dispatch(self, msg: Message) -> None:
        if msg.sender_id == self.user_id:
            log.debug("skipping own message %s", msg.id)
        else:
            handled = False
            for feature in self.features:
                try:
                    if feature.wants(msg):
                        handled = True
                        feature.handle(msg, self)
                except Exception:
                    log.exception("feature %s failed on message %s", feature.name, msg.id)
            if not handled and msg.command is not None:
                self.reply(msg, f"Sorry, I don't understand that. Try `@**{self.name}** help`.")
        with self._lock:
            self._state["last_message_id"] = max(self._state.get("last_message_id") or 0, msg.id)
            self._save_state()

    # ----- sending -----------------------------------------------------------------------

    def reply(self, msg: Message, content: str) -> None:
        """Reply where the message was: same channel and topic, or back into the DM."""
        if msg.is_dm:
            to = [i for i in msg.recipient_ids if i != self.user_id] or [msg.sender_id]
            self._send({"type": "private", "to": to, "content": content})
        else:
            self._send({"type": "stream", "to": msg.stream_id, "topic": msg.topic, "content": content})

    def post(self, channel: str, topic: str, content: str) -> None:
        self._send({"type": "stream", "to": channel, "topic": topic, "content": content})

    def _send(self, request: dict[str, Any]) -> None:
        result = self.client.send_message(request)
        if result.get("result") != "success":
            log.error("send failed: %s (%s)", result.get("msg"), request)

    # ----- catch-up after downtime -------------------------------------------------------

    def _catch_up(self) -> None:
        last_id = self._state.get("last_message_id")
        if last_id is None:
            newest = self._fetch(anchor="newest", num_before=1, num_after=0, narrow=[])
            with self._lock:
                self._state["last_message_id"] = newest[-1]["id"] if newest else 0
                self._save_state()
            log.info("first start, no catch-up")
            return
        since = time.time() - self.config.catch_up_hours * 3600
        for channel in self.watched_channels:
            own = self._fetch(
                anchor="newest",
                num_before=100,
                num_after=0,
                narrow=[{"operator": "stream", "operand": channel}, {"operator": "sender", "operand": self.email}],
            )
            for m in own:
                if m["timestamp"] >= since:
                    msg = Message.from_zulip(m, m.get("flags", []), self._mention_re)
                    for feature in self.features:
                        feature.remember_own(msg)
            missed = self._fetch(
                anchor=last_id or "oldest",
                num_before=0,
                num_after=CATCH_UP_BATCH,
                narrow=[{"operator": "stream", "operand": channel}],
            )
            for m in missed:
                if m["id"] > last_id and m["timestamp"] >= since:
                    log.info("catch-up: message %s in #%s", m["id"], channel)
                    self.dispatch(Message.from_zulip(m, m.get("flags", []), self._mention_re))

    def _fetch(self, **request: Any) -> list[dict[str, Any]]:
        result = self.client.get_messages({**request, "apply_markdown": False})
        if result.get("result") != "success":
            log.error("get_messages failed: %s (%s)", result.get("msg"), request)
            return []
        return result["messages"]

    # ----- scheduled features ------------------------------------------------------------

    def _scheduler_loop(self) -> None:
        while True:
            try:
                self.run_due_features()
            except Exception:
                log.exception("scheduler tick failed")
            time.sleep(SCHEDULER_TICK_S)

    def run_due_features(self, now: dt.datetime | None = None) -> list[str]:
        """Run every scheduled feature whose time has come today; returns the names run."""
        now = now or dt.datetime.now(self.tz)
        fired: list[str] = []
        for feature in self.scheduled:
            assert feature.at is not None
            if not is_due(feature.at, feature.grace, now, self._state.get("last_fired", {}).get(feature.name)):
                continue
            log.info("running scheduled feature %s", feature.name)
            try:
                feature.run(self)
            except Exception:
                log.exception("scheduled feature %s failed; will retry within its grace window", feature.name)
                continue
            with self._lock:
                self._state.setdefault("last_fired", {})[feature.name] = now.date().isoformat()
                self._save_state()
            fired.append(feature.name)
        return fired

    def run_feature_once(self, name: str) -> None:
        """Run one feature's scheduled body now (for an external cron)."""
        for feature in self.features:
            if feature.name == name:
                feature.run(self)
                return
        raise KeyError(f"no enabled feature named {name!r}; have {[f.name for f in self.features]}")

    # ----- state ---------------------------------------------------------------------------

    def feature_state(self, name: str) -> dict[str, Any]:
        """Persistent per-feature dictionary in the state file; call save_state after changing it."""
        return self._state.setdefault("features", {}).setdefault(name, {})

    def save_state(self) -> None:
        with self._lock:
            self._save_state()

    def _load_state(self) -> dict[str, Any]:
        if self._state_path.exists():
            return json.loads(self._state_path.read_text())
        return {}

    def _save_state(self) -> None:
        self._state_path.write_text(json.dumps(self._state, indent=2))
