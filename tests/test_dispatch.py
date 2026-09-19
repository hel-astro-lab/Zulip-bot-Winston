import json
import time

from tests.conftest import BOT_ID, FakeClient, dm_message, event, stream_message


def test_link_in_watched_channel_gets_card_in_same_topic(make_bot, fake_fetch):
    bot = make_bot()
    bot._on_event(event(stream_message(1, "look: https://arxiv.org/abs/2406.01234", topic="thermal")))
    assert fake_fetch == [["2406.01234"]]
    assert bot.client.sent == [
        {"type": "stream", "to": 7, "topic": "thermal", "content": bot.client.sent[0]["content"]}
    ]
    assert bot.client.sent[0]["content"].startswith("**Paper 2406.01234**")


def test_same_link_in_same_topic_is_answered_once(make_bot, fake_fetch):
    bot = make_bot()
    bot._on_event(event(stream_message(1, "https://arxiv.org/abs/2406.01234")))
    bot._on_event(event(stream_message(2, "> https://arxiv.org/abs/2406.01234\nnice one")))
    bot._on_event(event(stream_message(3, "https://arxiv.org/abs/2406.01234", topic="other")))
    assert fake_fetch == [["2406.01234"], ["2406.01234"]]
    assert len(bot.client.sent) == 2


def test_two_links_give_two_cards(make_bot, fake_fetch):
    bot = make_bot()
    bot._on_event(event(stream_message(1, "arXiv:2406.01234 vs arxiv.org/pdf/astro-ph/0601001")))
    assert fake_fetch == [["2406.01234", "astro-ph/0601001"]]
    assert len(bot.client.sent) == 2


def test_unwatched_channel_and_own_messages_are_ignored(make_bot, fake_fetch):
    bot = make_bot()
    bot._on_event(event(stream_message(1, "https://arxiv.org/abs/2406.01234", stream="general")))
    bot._on_event(event(stream_message(2, "https://arxiv.org/abs/2406.01234", sender=BOT_ID)))
    assert fake_fetch == [] and bot.client.sent == []


def test_unknown_paper_is_silent_in_channel_but_reported_on_command(make_bot, fake_fetch):
    bot = make_bot()
    bot._on_event(event(stream_message(1, "https://arxiv.org/abs/9999.99999")))
    assert bot.client.sent == []
    bot._on_event(event(dm_message(2, "arxiv 9999.99999")))
    assert bot.client.sent[-1] == {"type": "private", "to": [1], "content": "arXiv does not know `9999.99999`."}


def test_mention_help_and_unknown_command(make_bot):
    bot = make_bot()
    bot._on_event(event(stream_message(1, "@**Winston** help", stream="general", mentioned=True)))
    assert bot.client.sent[0]["to"] == 7
    assert "- **arxiv**:" in bot.client.sent[0]["content"] and "- **help**:" in bot.client.sent[0]["content"]
    assert "menu" not in bot.client.sent[0]["content"]  # disabled in the test config
    bot._on_event(event(stream_message(2, "hey @**Winston|99** what's up", stream="general", mentioned=True)))
    assert bot.client.sent[1]["content"].startswith("Sorry, I don't understand")


def test_dm_arxiv_command_with_bare_id(make_bot, fake_fetch):
    bot = make_bot()
    bot._on_event(event(dm_message(1, "arxiv 2406.01234")))
    assert fake_fetch == [["2406.01234"]]
    assert bot.client.sent[0]["type"] == "private" and bot.client.sent[0]["to"] == [1]
    bot._on_event(event(dm_message(2, "arxiv")))
    assert bot.client.sent[1]["content"].startswith("Usage:")


def test_fetch_failure_does_not_raise(make_bot, monkeypatch):
    from winston import arxiv

    def boom(ids):
        raise ConnectionError("no network")

    monkeypatch.setattr(arxiv, "fetch_papers", boom)
    bot = make_bot()
    bot._on_event(event(stream_message(1, "https://arxiv.org/abs/2406.01234")))
    assert bot.client.sent == []


def test_state_tracks_last_message_id(make_bot, tmp_path):
    bot = make_bot()
    bot._on_event(event(stream_message(41, "hello", stream="general")))
    bot._on_event(event(stream_message(40, "older", stream="general")))
    assert json.loads((tmp_path / "state.json").read_text())["last_message_id"] == 41


def test_first_start_records_newest_and_does_not_catch_up(make_bot, fake_fetch, tmp_path):
    client = FakeClient()
    client.history = [stream_message(5, "https://arxiv.org/abs/2406.01234")]
    bot = make_bot(client=client)
    bot._subscribe()
    bot._catch_up()
    assert client.subscribed == ["papers"]
    assert client.sent == [] and fake_fetch == []
    assert json.loads((tmp_path / "state.json").read_text())["last_message_id"] == 5


def test_catch_up_answers_missed_links_once(make_bot, fake_fetch):
    client = FakeClient()
    old = int(time.time()) - 3 * 24 * 3600
    client.history = [
        stream_message(10, "https://arxiv.org/abs/1111.11111"),  # already handled (id <= last)
        stream_message(11, "https://arxiv.org/abs/2406.01234"),  # missed, but Winston answered it before going down
        stream_message(12, "**Paper**\n[arXiv:2406.01234](https://arxiv.org/abs/2406.01234)", sender=BOT_ID),
        stream_message(13, "https://arxiv.org/abs/2222.22222", timestamp=old),  # too old
        stream_message(14, "https://arxiv.org/abs/3333.33333"),  # missed, unanswered
        stream_message(15, "https://arxiv.org/abs/4444.44444", stream="general"),  # not watched
    ]
    bot = make_bot(client=client, state={"last_message_id": 10})
    bot._catch_up()
    assert fake_fetch == [["3333.33333"]]
    assert len(client.sent) == 1 and client.sent[0]["topic"] == "reading"
    assert bot._state["last_message_id"] == 14
