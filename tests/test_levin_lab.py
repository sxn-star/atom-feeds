"""Tests for scrapers/levin_lab.py -- HTML parser logic."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapers.levin_lab import LevinLabScraper

FIXTURES = Path(__file__).parent / "fixtures"


def _soup(html: str):
    return BeautifulSoup(html, "lxml")


def _scraper():
    return LevinLabScraper()


# ---------------------------------------------------------------------------
# Helpers / fixture HTML
# ---------------------------------------------------------------------------

def _fixture_soup():
    return _soup((FIXTURES / "levin_lab_sample.html").read_text())


# ---------------------------------------------------------------------------
# Basic extraction from fixture
# ---------------------------------------------------------------------------

class TestParseFixture:
    def test_finds_four_papers(self):
        papers = _scraper()._parse(_fixture_soup())
        assert len(papers) == 4

    def test_first_paper_title(self):
        papers = _scraper()._parse(_fixture_soup())
        assert papers[0].title == "A Great Paper on Bioelectricity"

    def test_first_paper_authors(self):
        papers = _scraper()._parse(_fixture_soup())
        assert "Smith J." in papers[0].authors
        assert "Jones A.B." in papers[0].authors

    def test_first_paper_year(self):
        papers = _scraper()._parse(_fixture_soup())
        assert papers[0].year == 2024

    def test_first_paper_doi(self):
        papers = _scraper()._parse(_fixture_soup())
        assert papers[0].doi == "10.1038/example001"

    def test_first_paper_journal(self):
        papers = _scraper()._parse(_fixture_soup())
        assert papers[0].journal == "Nature"

    def test_first_paper_pdf_url(self):
        papers = _scraper()._parse(_fixture_soup())
        assert papers[0].pdf_url == "https://example.com/paper1.pdf"

    def test_year_inherited_from_heading(self):
        papers = _scraper()._parse(_fixture_soup())
        # Papers 0 and 1 are under <h2>2024</h2>
        assert papers[0].year == 2024
        assert papers[1].year == 2024
        # Papers 2 and 3 are under <h2>2023</h2>
        assert papers[2].year == 2023
        assert papers[3].year == 2023


# ---------------------------------------------------------------------------
# Abstract extraction from sibling paragraph
# ---------------------------------------------------------------------------

class TestAbstractExtraction:
    def test_abstract_captured_for_first_paper(self):
        papers = _scraper()._parse(_fixture_soup())
        assert "bioelectric" in papers[0].abstract.lower()

    def test_no_abstract_for_second_paper(self):
        # Second paper in fixture has no following abstract paragraph
        papers = _scraper()._parse(_fixture_soup())
        assert papers[1].abstract == ""

    def test_abstract_sibling_not_added_as_separate_paper(self):
        # The abstract <p> must be consumed and not appear as a paper itself
        papers = _scraper()._parse(_fixture_soup())
        titles = [p.title for p in papers]
        assert not any("bioelectric signals" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# Month extraction
# ---------------------------------------------------------------------------

class TestMonthExtraction:
    def test_month_extracted_from_citation_text(self):
        papers = _scraper()._parse(_fixture_soup())
        # Third paper in fixture has "March 2023" in the volume field
        assert papers[2].month == 3

    def test_default_month_when_absent(self):
        papers = _scraper()._parse(_fixture_soup())
        # First paper has no month name
        assert papers[0].month == 1

    def test_month_case_insensitive(self):
        html = """<html><body>
        <h2>2024</h2>
        <p>Doe J. (2024). <strong>Title</strong>. <em>J</em>, JULY 2024. doi: 10.1/x. <a href="https://x.com">PDF</a></p>
        </body></html>"""
        papers = _scraper()._parse(_soup(html))
        assert papers[0].month == 7


# ---------------------------------------------------------------------------
# Edge cases / filter conditions
# ---------------------------------------------------------------------------

class TestFilterConditions:
    def test_paragraph_without_bold_is_skipped(self):
        html = """<html><body>
        <h2>2024</h2>
        <p>No bold here. doi: 10.1/x.</p>
        </body></html>"""
        assert _scraper()._parse(_soup(html)) == []

    def test_paragraph_without_doi_or_pdf_is_skipped(self):
        html = """<html><body>
        <h2>2024</h2>
        <p>Author A. (2024). <strong>Title Without Links</strong>. <em>Journal</em>.</p>
        </body></html>"""
        assert _scraper()._parse(_soup(html)) == []

    def test_doi_only_paper_captured(self):
        html = """<html><body>
        <h2>2023</h2>
        <p>White E. (2023). <strong>Paper With Only DOI</strong>. doi: 10.1234/test.</p>
        </body></html>"""
        papers = _scraper()._parse(_soup(html))
        assert len(papers) == 1
        assert papers[0].doi == "10.1234/test"
        assert papers[0].pdf_url == ""

    def test_no_papers_before_year_heading(self):
        html = """<html><body>
        <p>Author A. (2024). <strong>Early Title</strong>. doi: 10.1/x.</p>
        <h2>2024</h2>
        <p>Author B. (2024). <strong>Late Title</strong>. doi: 10.1/y.</p>
        </body></html>"""
        papers = _scraper()._parse(_soup(html))
        # The first <p> has no current_year yet, so it's skipped
        assert len(papers) == 1
        assert papers[0].title == "Late Title"

    def test_year_from_parens_overrides_heading(self):
        html = """<html><body>
        <h2>2024</h2>
        <p>Author A. (2019). <strong>Old Paper Reposted</strong>. doi: 10.1/x. <a href="https://x.com">PDF</a></p>
        </body></html>"""
        papers = _scraper()._parse(_soup(html))
        assert papers[0].year == 2019


# ---------------------------------------------------------------------------
# _looks_like_abstract
# ---------------------------------------------------------------------------

class TestLooksLikeAbstract:
    def test_short_text_rejected(self):
        el = _soup("<p>Too short.</p>").find("p")
        assert _scraper()._looks_like_abstract(el) is False

    def test_bold_paragraph_rejected(self):
        el = _soup("<p><strong>Title</strong> with text that is long enough to pass the length check alone.</p>").find("p")
        assert _scraper()._looks_like_abstract(el) is False

    def test_doi_paragraph_rejected(self):
        el = _soup("<p>doi: 10.1234/test something else here that makes it long enough to pass the length check.</p>").find("p")
        assert _scraper()._looks_like_abstract(el) is False

    def test_valid_abstract_accepted(self):
        text = "This is a real abstract with sufficient length to demonstrate that bioelectric signals drive morphogenetic outcomes."
        el = _soup(f"<p>{text}</p>").find("p")
        assert _scraper()._looks_like_abstract(el) is True

    def test_non_p_element_rejected(self):
        el = _soup("<div>Long enough text here that would otherwise pass the abstract length threshold for detection.</div>").find("div")
        assert _scraper()._looks_like_abstract(el) is False
