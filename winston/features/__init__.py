"""Feature registry. Adding a feature: one module here, one entry in FEATURES."""

from winston.features.arxiv_links import ArxivLinks
from winston.features.base import Feature
from winston.features.digest import Digest
from winston.features.help import Help
from winston.features.menu import Menu

FEATURES: list[type[Feature]] = [ArxivLinks, Digest, Help, Menu]

__all__ = ["FEATURES", "Feature"]
