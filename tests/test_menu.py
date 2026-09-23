import datetime as dt

from tests.conftest import MENU_POST as EXPECTED
from tests.conftest import UNICAFE as FIXTURE
from tests.conftest import dm_message, event
from winston.features import menu as menu_module

WEDNESDAY = dt.date(2026, 9, 23)
SATURDAY = dt.date(2026, 9, 26)
MENU = {"channel": "general", "topic": "lunch"}


def test_configured_order_main_dishes_only():
    rows = menu_module.todays_menu(FIXTURE, ["Exactum", "Physicum", "Chemicum", "Nowhere"], WEDNESDAY)
    assert [title for title, _, _ in rows] == ["Exactum", "Chemicum"]  # Physicum has no lunch, Olivia is not listed
    chemicum = rows[1][2]
    assert "Whole grain rice" not in chemicum and "Berry dessert" not in chemicum
    assert chemicum[0] == "Miso-Mushroom Ratatouille 🌱"


def test_message_format():
    rows = menu_module.todays_menu(FIXTURE, menu_module.DEFAULT_RESTAURANTS, WEDNESDAY)
    assert menu_module.format_menu(WEDNESDAY, rows) == EXPECTED


def test_weekday_post(make_bot, fake_unicafe):
    bot = make_bot(menu=MENU)
    bot.run_feature_once("menu")
    assert bot.client.sent == [{"type": "stream", "to": "general", "topic": "lunch", "content": EXPECTED}]


def test_silent_on_weekend_and_empty_day(make_bot, fake_unicafe):
    bot = make_bot(menu=MENU)
    fake_unicafe(SATURDAY)
    bot.run_feature_once("menu")
    fake_unicafe(dt.date(2026, 9, 24))  # a Thursday with no menus in the fixture
    bot.run_feature_once("menu")
    assert bot.client.sent == []


def test_menu_command(make_bot, fake_unicafe):
    bot = make_bot(menu=MENU)
    bot._on_event(event(dm_message(1, "menu")))
    assert bot.client.sent[0]["content"] == EXPECTED
    fake_unicafe(SATURDAY)
    bot._on_event(event(dm_message(2, "Menu")))
    assert bot.client.sent[1]["content"].startswith("No lunch today.")
