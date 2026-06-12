"""
Scraper for The Levin Lab peer-reviewed publications.
Source: https://www.drmichaellevin.org/publications/
"""

from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import sync_playwright

from .base import BaseScraper, Paper


class LevinLabScraper(BaseScraper):
    FEED_SLUG     = "levin-lab-publications"
    FEED_TITLE    = "The Levin Lab – Peer-Reviewed Papers"
    FEED_SUBTITLE = (
        "Academic publications from Michael Levin (Tufts University) on "
        "bioelectricity, morphogenesis, developmental biology, and collective intelligence."
    )
    SOURCE_URL    = "https://www.drmichaellevin.org/publications/"
    AUTHOR_NAME   = "Michael Levin"
    AUTHOR_URI    = "https://www.drmichaellevin.org/"
    FEED_RIGHTS   = "© The Levin Lab. All rights reserved."

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _fetch_html(self) -> str:
        """Use a headless Chromium browser (site blocks plain requests)."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            )
            page.goto(self.SOURCE_URL, wait_until="networkidle", timeout=60_000)
            html = page.content()
            browser.close()
        return html

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def scrape(self) -> list[Paper]:
        from bs4 import BeautifulSoup

        html = self._fetch_html()
        soup = BeautifulSoup(html, "lxml")
        return self._parse(soup)

    def _parse(self, soup) -> list[Paper]:
        papers: list[Paper] = []
        current_year: Optional[int] = None

        # Walk top-level elements, tracking year from <h2> headers
        for el in soup.find_all(["h2", "p"]):
            text = el.get_text(strip=True)

            # Year heading?
            if el.name == "h2" and re.fullmatch(r"\d{4}", text):
                current_year = int(text)
                continue

            if not current_year or el.name != "p":
                continue

            paper = self._parse_paper_p(el, current_year)
            if paper:
                papers.append(paper)

        return papers

    # ------------------------------------------------------------------
    # Per-paragraph extraction
    # ------------------------------------------------------------------

    def _parse_paper_p(self, p_el, current_year: int) -> Optional[Paper]:
        """Extract a Paper from a <p> element, or return None if not a paper."""

        # --- PDF link -------------------------------------------------------
        pdf_url = ""
        for a in p_el.find_all("a"):
            link_text = a.get_text(strip=True).upper()
            href = (a.get("href") or "").strip()
            if "PDF" in link_text and href.startswith("http"):
                pdf_url = href
                break

        # --- Title (bold) ---------------------------------------------------
        bold = p_el.find("strong") or p_el.find("b")
        if not bold:
            return None
        title = bold.get_text(strip=True).rstrip(".").strip()
        if not title:
            return None

        # --- Full visible text for regex parsing ----------------------------
        full = p_el.get_text(separator=" ", strip=True)

        # --- Authors + year -------------------------------------------------
        title_pos = full.find(title)
        pre_title = full[:title_pos].strip() if title_pos >= 0 else ""

        year_match = re.search(r"\((\d{4})\)", pre_title)
        year = int(year_match.group(1)) if year_match else current_year

        # Strip trailing "(YEAR)" from author string
        authors = re.sub(r"\s*\(\d{4}\)\s*$", "", pre_title).strip().rstrip(",").strip()
        # Clean stray leading/trailing punctuation
        authors = authors.strip(".,; ")

        # --- Journal (italic) -----------------------------------------------
        italic = p_el.find("em") or p_el.find("i")
        journal = italic.get_text(strip=True).rstrip(",.").strip() if italic else ""

        # --- Volume / issue / pages -----------------------------------------
        # Text immediately after the journal italic span up to the doi or PDF
        post_title = full[title_pos + len(title):] if title_pos >= 0 else full
        # Strip leading punctuation
        post_title = post_title.lstrip(". ,")

        volume = ""
        if journal:
            vol_match = re.search(
                re.escape(journal) + r"[,.]?\s*(.+?)(?:doi:|PDF|$)",
                full, re.IGNORECASE
            )
            if vol_match:
                raw_vol = vol_match.group(1).strip().rstrip(".,")
                # Reject fragments that are too long (likely junk)
                if len(raw_vol) < 60:
                    volume = raw_vol

        # --- DOI ------------------------------------------------------------
        doi = ""
        doi_match = re.search(r"doi:\s*(10\.\S+)", full, re.IGNORECASE)
        if doi_match:
            doi = doi_match.group(1).rstrip(".,) ")

        # --- Require at least a title and some kind of link -----------------
        if not title or (not pdf_url and not doi):
            return None

        return Paper(
            title=title,
            authors=authors,
            year=year,
            pdf_url=pdf_url,
            journal=journal,
            volume=volume,
            doi=doi,
        )
