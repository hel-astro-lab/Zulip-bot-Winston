"""Daily cafeteria menu post. Scheduled; the menu fetch itself is still to be written."""

from __future__ import annotations

from winston.features.base import Feature


class Menu(Feature):
    name = "menu"
    description = "posts the university cafeteria menu every day"

    def run(self, bot):
        bot.post(self.settings["channel"], self.settings.get("topic", "lunch"), "Cafeteria menu: not implemented yet.")
