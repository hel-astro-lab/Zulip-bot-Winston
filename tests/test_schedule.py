import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from winston.bot import is_due

TZ = ZoneInfo("Europe/Helsinki")
AT = dt.time(11, 15)
GRACE = dt.timedelta(minutes=120)


def at(hour, minute, day=18):
    return dt.datetime(2026, 9, day, hour, minute, tzinfo=TZ)


def test_is_due_window():
    assert not is_due(AT, GRACE, at(11, 14), None)
    assert is_due(AT, GRACE, at(11, 15), None)
    assert is_due(AT, GRACE, at(11, 40), None)  # laptop woke up late, still within grace
    assert not is_due(AT, GRACE, at(13, 15), None)  # grace over
    assert is_due(AT, GRACE, at(11, 16), "2026-09-17")  # fired yesterday, due again today
    assert not is_due(AT, GRACE, at(11, 16), "2026-09-18")  # already fired today


MENU = {"enabled": True, "at": "11:15", "channel": "general", "topic": "lunch", "grace_minutes": 120}


def test_scheduler_fires_once_per_day(make_bot):
    bot = make_bot(menu=MENU)
    assert [f.name for f in bot.scheduled] == ["menu"]
    assert bot.run_due_features(at(11, 0)) == []
    assert bot.run_due_features(at(11, 20)) == ["menu"]
    assert bot.run_due_features(at(11, 21)) == []  # restart within the window: no duplicate
    assert bot.run_due_features(at(11, 20, day=19)) == ["menu"]
    assert bot.client.sent == [
        {"type": "stream", "to": "general", "topic": "lunch", "content": "Cafeteria menu: not implemented yet."}
    ] * 2
    assert bot._state["last_fired"] == {"menu": "2026-09-19"}


def test_failed_run_is_retried_next_tick(make_bot, monkeypatch):
    bot = make_bot(menu=MENU)
    calls = []

    def flaky(_bot):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("menu site down")

    monkeypatch.setattr(bot.scheduled[0], "run", flaky)
    assert bot.run_due_features(at(11, 20)) == []
    assert bot.run_due_features(at(11, 21)) == ["menu"]
    assert bot.run_due_features(at(11, 22)) == []


def test_run_feature_once_by_name(make_bot):
    bot = make_bot(menu=MENU)
    bot.run_feature_once("menu")
    assert bot.client.sent[0]["to"] == "general"
    with pytest.raises(KeyError):
        bot.run_feature_once("nope")
