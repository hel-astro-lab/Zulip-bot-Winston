"""Daily lunch menu: the main dishes of the configured Unicafe restaurants and Tornado, posted on weekdays."""

from __future__ import annotations

import datetime as dt
import logging
import re
from html import unescape
from typing import Any

import requests

from winston import arxiv
from winston.features.base import Feature

log = logging.getLogger(__name__)

API_URL = "https://unicafe.fi/wp-json/swiss/v1/restaurants/"
TIMEOUT_S = 30.0
SKIPPED_COURSES = {"Lisäke", "Jälkiruoka"}  # sides and desserts
DEFAULT_RESTAURANTS = ["Chemicum Teachers restaurant", "Chemicum", "Exactum", "Tornado"]
COMPASS_API_URL = "https://www.compass-group.fi/menuapi/day-menus"
# Compass Group restaurants by the section heading of their menu: (cost center, page)
COMPASS = {
    "Tornado": ("1254", "https://www.compass-group.fi/ravintolat-ja-ruokalistat/foodco/kaupungit/helsinki/ravintola-tornado/"),
}


def today(tz) -> dt.date:
    return dt.datetime.now(tz).date()


def fetch_restaurants(lang: str) -> list[dict[str, Any]]:
    """Every Unicafe restaurant with two weeks of menus, in one request."""
    response = requests.get(API_URL, params={"lang": lang}, headers={"User-Agent": arxiv.USER_AGENT}, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def fetch_compass_menu(cost_center: str, day: dt.date) -> str:
    """A Compass Group restaurant's hand-typed HTML menu for `day`, Finnish only; '' when closed or unreachable,
    so a Compass outage never holds back the Unicafe post."""
    try:
        response = requests.get(
            COMPASS_API_URL,
            params={"costCenter": cost_center, "date": day.isoformat(), "language": "fi"},
            headers={"User-Agent": arxiv.USER_AGENT},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json().get("html") or ""
    except requests.RequestException:
        log.warning("no Compass menu for cost center %s", cost_center, exc_info=True)
        return ""


def compass_dishes(html: str, section: str) -> list[str]:
    """Dishes under the `section` heading of a Compass menu. A line without ':' is a heading; dish lines read
    'Lounas 1  7.60€/11.90€ : Lihapullia (L.G) Kermakastiketta (L.G)'."""
    dishes, heading = [], None
    for line in unescape(re.sub(r"<[^>]+>", "", re.sub(r"</p>|<br\s*/?>", "\n", html))).splitlines():
        line = " ".join(line.split())
        if line and ":" not in line:
            heading = line
        elif line and heading == section:
            parts = re.split(r"\s*\(([^)]*)\)\s*", line.split(":", 1)[1])  # names alternate with diet codes
            dish = ", ".join(p.strip() for p in parts[0::2] if p.strip()).replace(", ja ", " ja ")
            # vegan when the main is; sides such as rice often lack the Veg code
            dishes.append(dish + (" 🌱" if len(parts) > 1 and re.search(r"\bveg\b", parts[1], re.I) else ""))
    if html and not dishes:
        log.warning("no %r section in the Compass menu", section)
    return dishes


def todays_menu(
    restaurants: list[dict[str, Any]], names: list[str], day: dt.date, compass_menus: dict[str, str] | None = None
) -> list[tuple[str, str, list[str]]]:
    """(title, url, dishes) for each named restaurant serving something on `day`, in the order of `names`.
    Unicafe restaurants come from `restaurants`, Compass ones from `compass_menus`: name -> that day's HTML menu."""
    by_title = {r["title"]: r for r in restaurants}
    compass_menus = compass_menus or {}
    rows = []
    for name in names:
        if name in compass_menus:
            title, url, dishes = name, COMPASS[name][1], compass_dishes(compass_menus[name], name)
        elif name in by_title:
            restaurant = by_title[name]
            menus = restaurant.get("menuData", {}).get("menus", [])
            today = next((m for m in menus if m["date"].endswith(f"{day:%d.%m.}")), None)
            title, url = restaurant["title"], restaurant["permalink"]
            dishes = [
                dish["name"].strip() + (" 🌱" if "Veg" in dish.get("meta", {}).get("0", []) else "")
                for dish in (today or {}).get("data", [])
                if dish.get("price", {}).get("name") not in SKIPPED_COURSES
            ]
        else:
            log.warning("no Unicafe restaurant titled %r", name)
            continue
        if dishes:
            rows.append((title, url, dishes))
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
        names = list(self.settings.get("restaurants", DEFAULT_RESTAURANTS))
        compass_menus = {name: fetch_compass_menu(COMPASS[name][0], day) for name in names if name in COMPASS}
        rows = todays_menu(restaurants, names, day, compass_menus)
        return format_menu(day, rows, self.settings.get("campus", "Kumpula"))

    def run(self, bot):
        message = self.todays_message(bot)
        if message:
            bot.post(self.settings["channel"], self.settings.get("topic", "Lunch"), message)

    def wants(self, msg):
        return msg.command is not None and msg.command.strip().lower() == "menu"

    def handle(self, msg, bot):
        bot.reply(msg, self.todays_message(bot) or "No lunch today. A professor forages; bring a banana.")
