import json

import pytest

from tests.conftest import dm_message, event, stream_message
from winston.features import secret as secret_module

SECRETS = "# header\nFirst secret.\n\nSecond secret.\n"


@pytest.fixture
def secret_bot(make_bot, monkeypatch, tmp_path):
    (tmp_path / "secrets.txt").write_text(SECRETS, encoding="utf-8")
    monkeypatch.setattr(secret_module, "today", lambda tz: "2026-09-19")
    monkeypatch.setattr(secret_module.random, "choice", lambda options: options[0])
    return make_bot()


def test_dm_secret_tells_one_and_records_it(secret_bot, tmp_path):
    secret_bot._on_event(event(dm_message(1, "secret", sender=5)))
    assert secret_bot.client.sent == [{"type": "private", "to": [5], "content": "First secret."}]
    state = json.loads((tmp_path / "state.json").read_text())["features"]["secret"]
    assert state == {"date": "2026-09-19", "last": "First secret.", "user": 5}


def test_only_one_secret_per_day_for_everyone(secret_bot):
    secret_bot._on_event(event(dm_message(1, "secret", sender=5)))
    secret_bot._on_event(event(dm_message(2, "Secret", sender=5)))
    secret_bot._on_event(event(dm_message(3, "secret", sender=6)))
    contents = [m["content"] for m in secret_bot.client.sent]
    assert contents[0] == "First secret."
    assert contents[1].startswith("Today's secret has already been told") and contents[2] == contents[1]
    assert secret_bot._state["features"]["secret"]["user"] == 5


def test_next_day_gives_a_different_secret(secret_bot, monkeypatch):
    secret_bot._on_event(event(dm_message(1, "secret")))
    monkeypatch.setattr(secret_module, "today", lambda tz: "2026-09-20")
    secret_bot._on_event(event(dm_message(2, "secret")))
    assert [m["content"] for m in secret_bot.client.sent] == ["First secret.", "Second secret."]


def test_channel_mention_is_refused_without_spending_the_day(secret_bot):
    secret_bot._on_event(event(stream_message(1, "@**Winston** secret", stream="general", mentioned=True)))
    assert secret_bot.client.sent[0]["to"] == 7 and secret_bot.client.sent[0]["content"].startswith("Not here.")
    assert not secret_bot._state.get("features", {}).get("secret", {}).get("date")
    secret_bot._on_event(event(dm_message(2, "secret")))
    assert secret_bot.client.sent[1]["content"] == "First secret."


@pytest.mark.parametrize("content", ["", "# only comments\n\n"])
def test_empty_or_missing_file_has_no_secrets(secret_bot, tmp_path, content):
    (tmp_path / "secrets.txt").write_text(content)
    secret_bot._on_event(event(dm_message(1, "secret")))
    assert secret_bot.client.sent[0]["content"].startswith("I have no secrets today")
    assert not secret_bot._state.get("features", {}).get("secret", {}).get("date")
    (tmp_path / "secrets.txt").unlink()
    secret_bot._on_event(event(dm_message(2, "secret")))
    assert secret_bot.client.sent[1]["content"].startswith("I have no secrets today")


def test_help_lists_secret(secret_bot):
    secret_bot._on_event(event(dm_message(1, "help")))
    assert "- **secret**:" in secret_bot.client.sent[0]["content"]
