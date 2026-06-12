"""
Scraper for Bernardo Kastrup's peer-reviewed academic papers.
Source: https://www.bernardokastrup.com/p/papers.html
"""

from __future__ import annotations

import re
from typing import Optional

from .base import BaseScraper, CacheHit, Paper


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

_DOI_RE = re.compile(r'(?:doi:\s*)?(10\.\d{4,}/\S+)', re.IGNORECASE)

# Link text values that are not paper titles
_LINK_NON_TITLES = frozenset(
    {"PDF", "DOI", "LINK", "HTML", "PREPRINT", "ACCESS PAPER", "OPEN ACCESS", "FULL TEXT"}
)


class KastrupScraper(BaseScraper):
    FEED_SLUG     = "kastrup-papers"
    FEED_TITLE    = "Bernardo Kastrup – Academic Papers"
    FEED_SUBTITLE = (
        "Peer-reviewed academic papers by Bernardo Kastrup on philosophy of mind, "
        "consciousness, analytic idealism, and the metaphysics of nature."
    )
    SOURCE_URL    = "https://www.bernardokastrup.com/p/papers.html"
    AUTHOR_NAME   = "Bernardo Kastrup"
    AUTHOR_URI    = "https://www.bernardokastrup.com/"
    FEED_RIGHTS   = "© Bernardo Kastrup. All rights reserved."

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _fetch_html(self) -> str:
        """Fetch the papers page with a headless browser (site blocks plain requests)."""
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
        # Blogger static pages put their content in .post-body / .entry-content
        content = (
            soup.find("div", class_="entry-content")
            or soup.find("div", class_="post-body")
            or soup.find("article")
            or soup.body
        )
        if content is None:
            return []

        candidates = self._gather_candidates(content)

        papers: list[Paper] = []
        current_year: Optional[int] = None

        i = 0
        while i < len(candidates):
            el = candidates[i]
            text = el.get_text(strip=True)

            # Year heading
            if el.name in ("h2", "h3", "h4") and re.fullmatch(r"\d{4}", text):
                current_year = int(text)
                i += 1
                continue

            if not text:
                i += 1
                continue

            paper = self._parse_entry(el, current_year)
            if paper:
                # Lookahead: next <p>/<li> without bold/link may be an abstract
                if i + 1 < len(candidates) and self._looks_like_abstract(candidates[i + 1]):
                    paper.abstract = candidates[i + 1].get_text(separator=" ", strip=True)
                    i += 1
                papers.append(paper)

            i += 1

        return papers

    def _gather_candidates(self, content) -> list:
        """Return heading and paragraph-level elements in document order.

        We recurse one level into <ul>/<ol> to collect <li> items, and into
        wrapper <div>s, while keeping the flat list free of nested duplicates
        (e.g. a <p> inside a <li> is not included separately).
        """
        results = []
        for el in content.children:
            name = getattr(el, "name", None)
            if name in ("h2", "h3", "h4", "p"):
                results.append(el)
            elif name in ("ul", "ol"):
                for li in el.find_all("li", recursive=False):
                    results.append(li)
            elif name == "div":
                results.extend(self._gather_candidates(el))
        return results

    def _looks_like_abstract(self, el) -> bool:
        """Return True if the element looks like a stand-alone abstract paragraph."""
        if el.name not in ("p", "li"):
            return False
        text = el.get_text(strip=True)
        if re.fullmatch(r"\d{4}", text):
            return False
        if el.find("strong") or el.find("b"):
            return False
        if _DOI_RE.search(text):
            return False
        return len(text) >= 80

    # ------------------------------------------------------------------
    # Per-entry extraction
    # ------------------------------------------------------------------

    def _parse_entry(self, el, current_year: Optional[int]) -> Optional[Paper]:
        full = el.get_text(separator=" ", strip=True)

        # --- Title: prefer bold/strong; fall back to a meaningful anchor ------
        bold = el.find("strong") or el.find("b")
        title = ""
        if bold:
            title = bold.get_text(strip=True).rstrip(".").strip()

        if not title:
            for a in el.find_all("a"):
                candidate = a.get_text(strip=True)
                href = a.get("href") or ""
                # Skip short strings, URLs rendered as text, and known non-titles
                if len(candidate) <= 15:
                    continue
                if re.match(r"https?://", candidate):
                    continue
                if candidate.upper() in _LINK_NON_TITLES:
                    continue
                # A plausible paper title
                title = candidate.rstrip(".").strip()
                break

        if not title:
            return None

        # --- Year -----------------------------------------------------------
        year = current_year
        year_in_parens = re.search(r"\((\d{4})\)", full)
        if year_in_parens:
            year = int(year_in_parens.group(1))
        if not year:
            bare_year = re.search(r"\b(20\d{2}|19\d{2})\b", full)
            if bare_year:
                year = int(bare_year.group(1))
        if not year:
            return None

        # --- Links: PDF / journal landing page / DOI ------------------------
        pdf_url = ""
        doi_href = ""
        for a in el.find_all("a"):
            href = (a.get("href") or "").strip()
            link_text = a.get_text(strip=True).upper()
            if not href.startswith("http"):
                continue
            if href.lower().endswith(".pdf") or "PDF" in link_text:
                pdf_url = pdf_url or href
            elif "DOI.ORG" in href.upper():
                doi_href = doi_href or href
            elif not pdf_url and link_text not in _LINK_NON_TITLES:
                # First non-DOI link with meaningful text → journal landing page
                if len(a.get_text(strip=True)) > 3:
                    pdf_url = href

        # --- DOI ------------------------------------------------------------
        doi = ""
        doi_text_match = re.search(r"doi:\s*(10\.\S+)", full, re.IGNORECASE)
        if doi_text_match:
            doi = doi_text_match.group(1).rstrip(".,) ")
        if not doi and doi_href:
            doi_href_match = re.search(r"(10\.\d{4,}/\S+)", doi_href)
            if doi_href_match:
                doi = doi_href_match.group(1).rstrip(".,) ")
        if not doi:
            bare_doi = _DOI_RE.search(full)
            if bare_doi:
                doi = bare_doi.group(1).rstrip(".,) ")

        # --- Authors --------------------------------------------------------
        title_pos = full.find(title)
        pre_title = full[:title_pos].strip() if title_pos >= 0 else ""
        authors = re.sub(r"\s*\(\d{4}\)\s*\.?\s*$", "", pre_title).strip().rstrip(".,; ").strip()
        if not authors:
            authors = self.AUTHOR_NAME

        # --- Month ----------------------------------------------------------
        month = 1
        month_match = _MONTH_RE.search(full)
        if month_match:
            month = _MONTH_MAP[month_match.group(1).lower()]

        # --- Journal (italic) -----------------------------------------------
        journal = ""
        italic = el.find("em") or el.find("i")
        if italic:
            j = italic.get_text(strip=True).rstrip(",.").strip()
            # Exclude very short strings, year-like strings, and publisher notes
            if len(j) > 3 and not re.match(r"^\d", j):
                journal = j

        # --- Volume ---------------------------------------------------------
        volume = ""
        if journal:
            vol_match = re.search(
                re.escape(journal) + r"[,.]?\s*(.+?)(?:\s*(?:doi:|PDF|\[|$))",
                full, re.IGNORECASE,
            )
            if vol_match:
                raw_vol = vol_match.group(1).strip().rstrip(".,")
                if raw_vol and len(raw_vol) < 60:
                    volume = raw_vol

        # --- Require at least a link or DOI to confirm it's a real entry ----
        if not (pdf_url or doi):
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
