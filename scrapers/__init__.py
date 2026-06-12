"""
Scraper registry.

All scrapers in this package are auto-discovered by generate_all.py via
the ALL_SCRAPERS list below.  To register a new feed, import it here and
add an instance to ALL_SCRAPERS.
"""

from .kastrup import KastrupScraper
from .levin_lab import LevinLabScraper

# Add new scraper instances here as you create them:
ALL_SCRAPERS = [
    KastrupScraper(),
    LevinLabScraper(),
]
