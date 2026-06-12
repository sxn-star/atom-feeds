"""Tests for scrapers/kastrup.py."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapers.kastrup import KastrupScraper

FIXTURE = Path(__file__).parent / "fixtures" / "kastrup_sample.html"


@pytest.fixture(scope="module")
def scraper():
    return KastrupScraper()


@pytest.fixture(scope="module")
def soup():
    return BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "lxml")


@pytest.fixture(scope="module")
def papers(scraper, soup):
    return scraper._parse(soup)


# ---------------------------------------------------------------------------
# Fixture parsing: top-level counts
# ---------------------------------------------------------------------------

class TestParseFixture:
    def test_returns_list(self, papers):
        assert isinstance(papers, list)

    def test_finds_six_papers(self, papers):
        assert len(papers) == 6

    def test_all_have_titles(self, papers):
        assert all(p.title for p in papers)

    def test_all_have_years(self, papers):
        assert all(p.year > 0 for p in papers)

    def test_all_have_doi_or_pdf(self, papers):
        for p in papers:
            assert p.doi or p.pdf_url, f"no link for: {p.title}"


# ---------------------------------------------------------------------------
# Per-paper: first paper (2023, plain DOI anchor + journal link)
# ---------------------------------------------------------------------------

class TestFirstPaper:
    def test_title(self, papers):
        assert papers[0].title == "The Collapse of Materialism"

    def test_year(self, papers):
        assert papers[0].year == 2023

    def test_journal(self, papers):
        assert papers[0].journal == "Journal of Consciousness Studies"

    def test_doi(self, papers):
        assert papers[0].doi == "10.53765/20700121.30.34.001"

    def test_author_solo(self, papers):
        assert "Kastrup" in papers[0].authors

    def test_volume(self, papers):
        assert papers[0].volume != ""


# ---------------------------------------------------------------------------
# Per-paper: second paper (2023, doi: + PDF link)
# ---------------------------------------------------------------------------

class TestSecondPaper:
    def test_title(self, papers):
        assert papers[1].title == "Analytic Idealism and the Problem of Other Minds"

    def test_year(self, papers):
        assert papers[1].year == 2023

    def test_journal(self, papers):
        assert papers[1].journal == "Philosophies"

    def test_doi(self, papers):
        assert papers[1].doi == "10.3390/philosophies8020022"

    def test_pdf_url(self, papers):
        assert "pdf" in papers[1].pdf_url.lower()


# ---------------------------------------------------------------------------
# Co-author paper (index 2)
# ---------------------------------------------------------------------------

class TestCoAuthorPaper:
    def test_title(self, papers):
        assert "Physicalism" in papers[2].title

    def test_year(self, papers):
        assert papers[2].year == 2022

    def test_authors_include_both(self, papers):
        assert "Kastrup" in papers[2].authors
        assert "Woollacott" in papers[2].authors

    def test_journal(self, papers):
        assert papers[2].journal == "Entropy"

    def test_doi(self, papers):
        assert papers[2].doi.startswith("10.")


# ---------------------------------------------------------------------------
# No-PDF paper (doi only, index 3)
# ---------------------------------------------------------------------------

class TestDoiOnlyPaper:
    def test_title(self, papers):
        assert papers[3].title == "On the Plausibility of Idealism"

    def test_has_doi(self, papers):
        assert papers[3].doi != ""

    def test_no_pdf(self, papers):
        assert papers[3].pdf_url == ""


# ---------------------------------------------------------------------------
# Month extraction (index 4 has "May 2022" in title)
# ---------------------------------------------------------------------------

class TestMonthExtraction:
    def test_month_may(self, papers):
        assert papers[4].month == 5

    def test_year_still_correct(self, papers):
        assert papers[4].year == 2022


# ---------------------------------------------------------------------------
# List-item paper (index 5, inside <ul><li>)
# ---------------------------------------------------------------------------

class TestListItemPaper:
    def test_title(self, papers):
        assert papers[5].title == "What is Matter to an Idealist?"

    def test_year(self, papers):
        assert papers[5].year == 2021

    def test_journal(self, papers):
        assert "Journal of Consciousness Studies" in papers[5].journal

    def test_doi(self, papers):
        assert papers[5].doi.startswith("10.")


# ---------------------------------------------------------------------------
# _looks_like_abstract
# ---------------------------------------------------------------------------

class TestLooksLikeAbstract:
    def test_long_prose_is_abstract(self, scraper, soup):
        from bs4 import BeautifulSoup as BS
        el = BS('<p>This paper argues that the mind is the only substance that exists, '
                'making a case for analytic idealism as a metaphysical framework consistent '
                'with modern science and philosophy of mind.</p>', "lxml").find("p")
        assert scraper._looks_like_abstract(el) is True

    def test_short_text_is_not_abstract(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS("<p>Short text.</p>", "lxml").find("p")
        assert scraper._looks_like_abstract(el) is False

    def test_four_digit_year_is_not_abstract(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS("<p>2023</p>", "lxml").find("p")
        assert scraper._looks_like_abstract(el) is False

    def test_bold_title_is_not_abstract(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS("<p><strong>Title of Paper</strong> more citation text here blah blah blah "
                "blah blah blah blah blah blah blah blah blah.</p>", "lxml").find("p")
        assert scraper._looks_like_abstract(el) is False

    def test_doi_line_is_not_abstract(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS("<p>doi: 10.1234/some.doi.here blah blah blah blah blah blah blah blah "
                "blah blah blah blah blah blah blah blah blah blah blah blah</p>",
                "lxml").find("p")
        assert scraper._looks_like_abstract(el) is False

    def test_heading_is_not_abstract(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS("<h3>2022</h3>", "lxml").find("h3")
        assert scraper._looks_like_abstract(el) is False


# ---------------------------------------------------------------------------
# Year extraction edge cases
# ---------------------------------------------------------------------------

class TestYearExtraction:
    def test_year_from_parentheses(self, scraper, soup):
        from bs4 import BeautifulSoup as BS
        el = BS('<p>Kastrup, B. (2019). <strong>Some Title</strong>. '
                '<em>Journal</em>, 5(1), 1–10. doi: 10.1234/j.2019.001</p>', "lxml").find("p")
        paper = scraper._parse_entry(el, None)
        assert paper is not None
        assert paper.year == 2019

    def test_year_from_heading_fallback(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS('<p><strong>Some Title Without Year</strong>. '
                '<em>Journal</em>. doi: 10.1234/j.001</p>', "lxml").find("p")
        paper = scraper._parse_entry(el, 2018)
        assert paper is not None
        assert paper.year == 2018

    def test_no_year_returns_none(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS('<p><strong>Some Title Without Year</strong>. '
                '<em>Journal</em>. doi: 10.1234/j.001</p>', "lxml").find("p")
        paper = scraper._parse_entry(el, None)
        assert paper is None


# ---------------------------------------------------------------------------
# Default author fallback
# ---------------------------------------------------------------------------

class TestAuthorFallback:
    def test_sole_author_defaults_to_kastrup(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS('<p>(2020). <strong>A Title With No Author Prefix</strong>. '
                '<em>Some Journal</em>. doi: 10.9999/x.2020</p>', "lxml").find("p")
        paper = scraper._parse_entry(el, 2020)
        assert paper is not None
        assert paper.authors == "Bernardo Kastrup"

    def test_coauthor_preserved(self, scraper):
        from bs4 import BeautifulSoup as BS
        el = BS('<p>Kastrup, B. &amp; Smith, J. (2021). <strong>Collaboration</strong>. '
                '<em>Journal X</em>, 1(1), 1. doi: 10.1234/x.2021</p>', "lxml").find("p")
        paper = scraper._parse_entry(el, 2021)
        assert paper is not None
        assert "Smith" in paper.authors


# ---------------------------------------------------------------------------
# Metadata constants
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_feed_slug(self, scraper):
        assert scraper.FEED_SLUG == "kastrup-papers"

    def test_feed_title(self, scraper):
        assert "Kastrup" in scraper.FEED_TITLE

    def test_source_url(self, scraper):
        assert scraper.SOURCE_URL == "https://www.bernardokastrup.com/p/papers.html"

    def test_author_name(self, scraper):
        assert scraper.AUTHOR_NAME == "Bernardo Kastrup"
