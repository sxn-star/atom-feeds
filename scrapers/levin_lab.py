"""
Scraper for The Levin Lab peer-reviewed publications.
Source: https://www.drmichaellevin.org/publications/
"""

from __future__ import annotations

import re
from typing import Optional

from .base import BaseScraper, CacheHit, Paper


# Month name -> integer, used to extract publication month from citation text.
_MONTH_MAP: dict[str, int] = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_MONTH_RE = re.compile(
    r'\b(' + '|'.join(_MONTH_MAP) + r')\b',
    re.IGNORECASE,
)


class LevinLabScraper(BaseScraper):
    FEED_SLUG     = "levin-lab-publications"
    FEED_TITLE    = "The Levin Lab - Peer-Reviewed Papers"
    FEED_SUBTITLE = (
        "Academic publications from Michael Levin (Tufts University) on "
        "bioelectricity, morphogenesis, developmental biology, and collective intelligence."
    )
    SOURCE_URL    = "https://www.drmichaellevin.org/publications/"
    AUTHOR_NAME   = "Michael Levin"
    AUTHOR_URI    = "https://www.drmichaellevin.org/"
    FEED_RIGHTS   = "(c) The Levin Lab. All rights reserved."

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _fetch_html(self) -> str:
        """Fetch the publications page with a headless browser (site blocks plain requests).

        Raises CacheHit if the rendered HTML is byte-for-byte identical to the
        last successful fetch, so the caller can skip an unnecessary re-parse.
        """
        from playwright.sync_api import sync_playwright
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

        if self._check_html_cache(html):
            raise CacheHit()
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

        all_elements = soup.find_all(["h2", "p"])
        i = 0
        while i < len(all_elements):
            el = all_elements[i]
            text = el.get_text(strip=True)

            # Year heading
            if el.name == "h2" and re.fullmatch(r"\d{4}", text):
                current_year = int(text)
                i += 1
                continue

            if not current_year or el.name != "p":
                i += 1
                continue

            paper = self._parse_paper_p(el, current_year)
            if paper:
                # Look ahead: if the next <p> has no bold title and looks like
                # prose, treat it as the abstract for this citation.
                if i + 1 < len(all_elements) and self._looks_like_abstract(all_elements[i + 1]):
                    paper.abstract = all_elements[i + 1].get_text(separator=" ", strip=True)
                    i += 1  # consume the abstract element
                papers.append(paper)

            i += 1

        return papers

    # ------------------------------------------------------------------
    # Abstract detection
    # ------------------------------------------------------------------

    def _looks_like_abstract(self, el) -> bool:
        """Return True if a paragraph element looks like a stand-alone abstract."""
        if el.name != "p":
            return False
        text = el.get_text(strip=True)
        # Year headings and citation paragraphs (which have bold titles) are excluded
        if re.fullmatch(r"\d{4}", text):
            return False
        if el.find("strong") or el.find("b"):
            return False
        # A DOI line is a continuation of the citation, not an abstract
        if re.search(r'\bdoi:\s*10\.', text, re.IGNORECASE):
            return False
        return len(text) >= 80

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

        authors = re.sub(r"\s*\(\d{4}\)\s*$", "", pre_title).strip().rstrip(",").strip()
        authors = authors.strip(".,; ")

        # --- Publication month (best-effort) --------------------------------
        month = 1
        month_match = _MONTH_RE.search(full)
        if month_match:
            month = _MONTH_MAP[month_match.group(1).lower()]

        # --- Journal (italic) -----------------------------------------------
        italic = p_el.find("em") or p_el.find("i")
        journal = italic.get_text(strip=True).rstrip(",.").strip() if italic else ""

        # --- Volume / issue / pages -----------------------------------------
        volume = ""
        if journal:
            vol_match = re.search(
                re.escape(journal) + r"[,.]?\s*(.+?)(?:doi:|PDF|$)",
                full, re.IGNORECASE
            )
            if vol_match:
                raw_vol = vol_match.group(1).strip().rstrip(".,")
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
            month=month,
        )
