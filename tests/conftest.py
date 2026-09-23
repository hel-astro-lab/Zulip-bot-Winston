import datetime as dt
import json
import time
from pathlib import Path

import pytest

from winston import arxiv
from winston.bot import Config, Winston
from winston.features import menu

UNICAFE = json.loads((Path(__file__).parent / "fixtures" / "unicafe.json").read_text(encoding="utf-8"))
MENU_POST = """\
**Lunch at Kumpula, Wednesday 23 September**
- [Chemicum Teachers restaurant](https://unicafe.fi/en/restaurants/chemicum-teachers-restaurant/):
    - Miso-Mushroom Ratatouille 🌱
    - Chicken lasagna with mascarpone
    - Haudutettua punakaalia 🌱
- [Chemicum](https://unicafe.fi/en/restaurants/chemicum/):
    - Miso-Mushroom Ratatouille 🌱
    - Beatrootballs, wasabi-sauce 🌱
    - Chicken lasagna with mascarpone
- [Exactum](https://unicafe.fi/en/restaurants/exactum/):
    - Kasviskepukoita & raikasta maissisalsaa 🌱
    - Chili con Unlimited Jauhis 🌱
    - Kreikkalainen tomaattikeitto 🌱
    - Meksikolaista broileria ja maissisalsaa"""

BOT_ID = 99
BOT_EMAIL = "winston-bot@example.com"


class FakeClient:
    """Just enough of zulip.Client for the bot: profile, subscriptions, sending, history."""

    def __init__(self):
        self.sent = []
        self.subscribed = []
        self.history = []  # dicts in Zulip message shape, returned by get_messages

    def get_profile(self):
        return {"user_id": BOT_ID, "email": BOT_EMAIL, "full_name": "Winston"}

    def add_subscriptions(self, streams):
        self.subscribed += [s["name"] for s in streams]
        return {"result": "success"}

    def send_message(self, request):
        self.sent.append(request)
        return {"result": "success", "id": len(self.sent)}

    def get_messages(self, request):
        assert request["apply_markdown"] is False
        messages = self.history
        for clause in request["narrow"]:
            if clause["operator"] == "stream":
                messages = [m for m in messages if m.get("display_recipient") == clause["operand"]]
            elif clause["operator"] == "sender":
                messages = [m for m in messages if m["sender_email"] == clause["operand"]]
        if request["anchor"] == "newest":
            messages = messages[-request["num_before"]:] if request["num_before"] else []
        elif request["anchor"] == "oldest":
            messages = messages[: request["num_after"]]
        else:
            messages = [m for m in messages if m["id"] >= request["anchor"]][: request["num_after"] + 1]
        return {"result": "success", "messages": messages}


def stream_message(id, content, *, sender=1, stream="papers", topic="reading", mentioned=False, timestamp=None):
    return {
        "id": id,
        "sender_id": sender,
        "sender_email": BOT_EMAIL if sender == BOT_ID else f"user{sender}@example.com",
        "type": "stream",
        "content": content,
        "timestamp": timestamp if timestamp is not None else int(time.time()),
        "stream_id": 7,
        "display_recipient": stream,
        "subject": topic,
        "flags": ["mentioned"] if mentioned else [],
    }


def dm_message(id, content, *, sender=1):
    return {
        "id": id,
        "sender_id": sender,
        "sender_email": f"user{sender}@example.com",
        "type": "private",
        "content": content,
        "timestamp": int(time.time()),
        "display_recipient": [{"id": sender}, {"id": BOT_ID}],
        "flags": [],
    }


def event(message):
    return {"type": "message", "id": 0, "message": message, "flags": message.get("flags", [])}


def paper(arxiv_id, n_authors=2):
    return arxiv.Paper(
        id=arxiv_id,
        title=f"Paper {arxiv_id}",
        authors=tuple(f"Author {i}" for i in range(n_authors)),
        abstract="Something interesting.",
        primary_category="astro-ph.HE",
        published=dt.date(2024, 6, 3),
    )


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replace the network fetch; records requested ids, returns a card for each."""
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return [paper(i) for i in ids if i != "9999.99999"]

    monkeypatch.setattr(arxiv, "fetch_papers", fetch)
    return calls


@pytest.fixture
def fake_unicafe(monkeypatch):
    """Serve the Unicafe fixture instead of the API, with today Wed 23.9.2026; returns a setter for today."""
    monkeypatch.setattr(menu, "fetch_restaurants", lambda lang: UNICAFE)

    def set_day(day):
        monkeypatch.setattr(menu, "today", lambda tz: day)

    set_day(dt.date(2026, 9, 23))
    return set_day


@pytest.fixture
def make_bot(tmp_path):
    def factory(client=None, state=None, **feature_settings):
        features = {"arxiv": {"channels": ["papers"]}, "menu": {"enabled": False}}
        features.update(feature_settings)
        config = Config(path=tmp_path / "winston.toml", timezone="Europe/Helsinki", features=features)
        if state is not None:
            import json

            (tmp_path / "state.json").write_text(json.dumps(state))
        client = client or FakeClient()
        return Winston(config, client=client)

    return factory
