"""
Base classes for all feed scrapers.

To add a new feed:
1. Create scrapers/your_source.py
2. Subclass BaseScraper
3. Implement scrape() -> list[Paper]
4. Set the class-level metadata constants
5. Register it in scrapers/__init__.py
"""

from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Sentinel exception
# ---------------------------------------------------------------------------

class CacheHit(Exception):
    """Raised by a scraper when the fetched page matches its stored hash.

    write_feed() catches this and skips the re-parse/re-write, leaving the
    existing .atom file untouched so git sees no diff.
    """


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Paper:
    """Represents a single academic paper entry."""
    title:   str
    authors: str          # free-form author string, e.g. "Last F., Last F., ..."
    year:    int
    pdf_url: str          # link to full text / PDF landing page

    journal:  str = ""
    volume:   str = ""    # e.g. "184(8): 1971-1989"
    doi:      str = ""    # bare DOI, e.g. "10.1038/s41586-023-00001-0"
    month:    int = 1
    abstract: str = ""

    @property
    def entry_id(self) -> str:
        """Stable Atom entry ID derived from title + year."""
        h = hashlib.md5(f"{self.title}{self.year}".encode()).hexdigest()[:8]
        return f"tag:atom-feeds,{self.year}:paper/{h}"

    @property
    def doi_url(self) -> str:
        return f"https://doi.org/{self.doi}" if self.doi else ""

    @property
    def published_date(self) -> str:
        return f"{self.year}-{self.month:02d}-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Abstract base scraper
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """
    Subclass this, set the metadata constants, implement scrape().
    Call write_feed(output_dir) to produce the .atom file.
    """

    # -- Required metadata --------------------------------------------------
    FEED_SLUG:     str   # filename stem, e.g. "levin-lab-publications"
    FEED_TITLE:    str   # e.g. "The Levin Lab - Peer-Reviewed Papers"
    FEED_SUBTITLE: str   # one-sentence description
    SOURCE_URL:    str   # the page being scraped (shown as alternate link)
    AUTHOR_NAME:   str   # primary author / lab name
    AUTHOR_URI:    str   # author's homepage

    # -- Optional overrides -------------------------------------------------
    FEED_RIGHTS: str = "All rights reserved."

    # Set by write_feed() before calling scrape(); readable by subclass scrapers
    _cache_dir: Optional[Path] = None

    # -----------------------------------------------------------------------

    @abstractmethod
    def scrape(self) -> list[Paper]:
        """Fetch the source page and return a list of Paper objects."""
        ...

    # -----------------------------------------------------------------------
    # Self-link resolution
    # -----------------------------------------------------------------------

    def _self_link(self) -> str:
        """Return the canonical feed URL, using GITHUB_REPOSITORY env var when available."""
        repo = os.environ.get("GITHUB_REPOSITORY", "YOUR_GITHUB_USERNAME/atom-feeds")
        return f"https://raw.githubusercontent.com/{repo}/main/feeds/{self.FEED_SLUG}.atom"

    # -----------------------------------------------------------------------
    # HTML page caching (opt-in for scraper subclasses)
    # -----------------------------------------------------------------------

    def _check_html_cache(self, html: str) -> bool:
        """Return True (cache hit) if html matches the stored SHA-256; otherwise save the new hash.

        Subclass scrapers that do expensive page fetches (e.g. Playwright) should
        call this right after fetching and raise CacheHit() when it returns True.
        """
        if self._cache_dir is None:
            return False
        cache_dir = Path(self._cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{self.FEED_SLUG}.sha256"
        new_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        if cache_file.exists() and cache_file.read_text().strip() == new_hash:
            return True
        cache_file.write_text(new_hash)
        return False

    # -----------------------------------------------------------------------
    # Atom XML generation
    # -----------------------------------------------------------------------

    def _esc(self, s: str) -> str:
        """Escape for use in XML text content."""
        return (s
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def _build_feed(self, papers: list[Paper]) -> str:
        updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        e = self._esc
        lines: list[str] = []

        lines += [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom"',
            '      xmlns:dc="http://purl.org/dc/elements/1.1/">',
            '',
            f'  <title>{e(self.FEED_TITLE)}</title>',
            f'  <subtitle>{e(self.FEED_SUBTITLE)}</subtitle>',
            f'  <link href="{e(self.SOURCE_URL)}" rel="alternate" type="text/html"/>',
            f'  <link href="{e(self._self_link())}"',
            f'        rel="self" type="application/atom+xml"/>',
            f'  <updated>{updated}</updated>',
            f'  <id>{e(self.SOURCE_URL)}</id>',
            f'  <rights>{e(self.FEED_RIGHTS)}</rights>',
            f'  <generator>atom-feeds scraper</generator>',
            '  <author>',
            f'    <name>{e(self.AUTHOR_NAME)}</name>',
            f'    <uri>{e(self.AUTHOR_URI)}</uri>',
            '  </author>',
        ]

        for p in papers:
            lines.append('')
            lines.append('  <entry>')
            lines.append(f'    <id>{e(p.entry_id)}</id>')
            lines.append(f'    <title type="text">{e(p.title)}</title>')
            lines.append(f'    <published>{p.published_date}</published>')
            lines.append(f'    <updated>{p.published_date}</updated>')

            # Single <author> element keeps the full author string intact.
            # Splitting on commas is fragile with academic name formats (initials,
            # "Jr.", hyphenated surnames, etc.).
            if p.authors:
                lines.append(f'    <author><name>{e(p.authors)}</name></author>')

            # Links
            if p.pdf_url:
                lines.append(f'    <link rel="alternate" type="text/html" href="{e(p.pdf_url)}"/>')
            if p.doi_url:
                lines.append(f'    <link rel="related" title="DOI" href="{e(p.doi_url)}"/>')

            # Categories
            if p.journal:
                lines.append(f'    <category term="{e(p.journal)}" label="{e(p.journal)}"/>')
            lines.append('    <category term="peer-reviewed" label="Peer-Reviewed"/>')

            # Rich HTML summary
            summary = self._build_summary(p)
            lines.append(f'    <summary type="html">{summary}</summary>')

            lines.append('  </entry>')

        lines += ['', '</feed>', '']
        return '\n'.join(lines)

    def _build_summary(self, p: Paper) -> str:
        e = self._esc
        parts = [f'{e(p.authors)} ({p.year}).']
        parts.append(f' &lt;strong&gt;{e(p.title)}&lt;/strong&gt;.')
        if p.journal:
            parts.append(f' &lt;em&gt;{e(p.journal)}&lt;/em&gt;')
            if p.volume:
                parts.append(f', {e(p.volume)}')
            parts.append('.')
        if p.doi:
            parts.append(f' DOI: &lt;a href=&quot;{e(p.doi_url)}&quot;&gt;{e(p.doi)}&lt;/a&gt;.')
        if p.pdf_url:
            parts.append(f' &lt;a href=&quot;{e(p.pdf_url)}&quot;&gt;Access paper &rarr;&lt;/a&gt;')
        if p.abstract:
            parts.append(f'&lt;p&gt;{e(p.abstract)}&lt;/p&gt;')
        return ''.join(parts)

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def write_feed(self, output_dir: Path) -> Path:
        """Scrape, generate Atom XML, write to output_dir/FEED_SLUG.atom.

        Sets self._cache_dir before calling scrape() so subclasses can use
        _check_html_cache().  Catches CacheHit to skip the write when the
        source page hasn't changed since the last run.
        """
        self._cache_dir = output_dir / ".cache"
        slug = self.FEED_SLUG
        print(f"[{slug}] scraping {self.SOURCE_URL} ...")

        try:
            papers = self.scrape()
        except CacheHit:
            print(f"[{slug}] page unchanged (cache hit) -- skipping")
            return output_dir / f"{slug}.atom"

        print(f"[{slug}] got {len(papers)} papers")
        xml = self._build_feed(papers)
        out_path = output_dir / f"{slug}.atom"
        out_path.write_text(xml, encoding="utf-8")
        print(f"[{slug}] wrote {out_path}")
        return out_path
