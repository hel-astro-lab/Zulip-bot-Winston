"""Daily Unicafe lunch menu: the main dishes of the configured restaurants, posted on weekdays."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import requests

from winston import arxiv
from winston.features.base import Feature

log = logging.getLogger(__name__)

API_URL = "https://unicafe.fi/wp-json/swiss/v1/restaurants/"
TIMEOUT_S = 30.0
SKIPPED_COURSES = {"Lisäke", "Jälkiruoka"}  # sides and desserts
DEFAULT_RESTAURANTS = ["Chemicum Teachers restaurant", "Chemicum", "Exactum"]


def today(tz) -> dt.date:
    return dt.datetime.now(tz).date()


def fetch_restaurants(lang: str) -> list[dict[str, Any]]:
    """Every Unicafe restaurant with two weeks of menus, in one request."""
    response = requests.get(API_URL, params={"lang": lang}, headers={"User-Agent": arxiv.USER_AGENT}, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def todays_menu(restaurants: list[dict[str, Any]], names: list[str], day: dt.date) -> list[tuple[str, str, list[str]]]:
    """(title, url, dishes) for each named restaurant serving something on `day`, in the order of `names`."""
    by_title = {r["title"]: r for r in restaurants}
    rows = []
    for name in names:
        restaurant = by_title.get(name)
        if restaurant is None:
            log.warning("no Unicafe restaurant titled %r", name)
            continue
        menus = restaurant.get("menuData", {}).get("menus", [])
        today = next((m for m in menus if m["date"].endswith(f"{day:%d.%m.}")), None)
        dishes = [
            dish["name"].strip() + (" 🌱" if "Veg" in dish.get("meta", {}).get("0", []) else "")
            for dish in (today or {}).get("data", [])
            if dish.get("price", {}).get("name") not in SKIPPED_COURSES
        ]
        if dishes:
            rows.append((restaurant["title"], restaurant["permalink"], dishes))
    return rows


def format_menu(day: dt.date, rows: list[tuple[str, str, list[str]]], campus: str = "Kumpula") -> str | None:
    if not rows:
        return None
    lines = [f"**Lunch at {campus}, {day:%A} {day.day} {day:%B}**"]
    for title, url, dishes in rows:
        lines.append(f"- [{title}]({url}):")
        lines += [f"    - {dish}" for dish in dishes]
    return "\n".join(lines)


class Menu(Feature):
    name = "menu"
    description = "I post the lunch menu each day and grade it on a scale from banana to no banana"

    def todays_message(self, bot) -> str | None:
        """Today's menu, or None on a weekend or when nothing is served."""
        day = today(bot.tz)
        if day.weekday() >= 5:
            return None
        restaurants = fetch_restaurants(self.settings.get("lang", "en"))
        rows = todays_menu(restaurants, list(self.settings.get("restaurants", DEFAULT_RESTAURANTS)), day)
        return format_menu(day, rows, self.settings.get("campus", "Kumpula"))

    def run(self, bot):
        message = self.todays_message(bot)
        if message:
            bot.post(self.settings["channel"], self.settings.get("topic", "Lunch"), message)

    def wants(self, msg):
        return msg.command is not None and msg.command.strip().lower() == "menu"

    def handle(self, msg, bot):
        bot.reply(msg, self.todays_message(bot) or "No lunch today. A professor forages; bring a banana.")
