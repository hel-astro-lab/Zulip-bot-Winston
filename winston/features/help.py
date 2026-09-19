"""`help`: list what Winston can do."""

from __future__ import annotations

from winston.features.base import Feature


class Help(Feature):
    name = "help"
    description = "`help` lists what I can do"

    def wants(self, msg):
        return msg.command is not None and msg.command.strip().lower() in ("", "help")

    def handle(self, msg, bot):
        lines = [f"G'day! {bot.name} here, professor, primate, and pillar of the astroplasma community. Here is what I can do for you:"]
        lines += [f"- **{feature.name}**: {feature.description}" for feature in bot.features]
        bot.reply(msg, "\n".join(lines))
