"""`help`: list what Winston can do."""

from __future__ import annotations

from winston.features.base import Feature


class Help(Feature):
    name = "help"
    description = "`help` lists what I can do"

    def wants(self, msg):
        return msg.command is not None and msg.command.strip().lower() in ("", "help")

    def handle(self, msg, bot):
        lines = [f"Hi, I'm {bot.name}. Here is what I do:"]
        lines += [f"- **{feature.name}**: {feature.description}" for feature in bot.features]
        bot.reply(msg, "\n".join(lines))
