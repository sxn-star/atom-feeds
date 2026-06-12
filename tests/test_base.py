"""Tests for scrapers/base.py -- Paper dataclass and BaseScraper helpers."""

import os
import re
from pathlib import Path

import pytest

from scrapers.base import BaseScraper, CacheHit, Paper


# ---------------------------------------------------------------------------
# Minimal concrete scraper for testing abstract methods
# ---------------------------------------------------------------------------

class _Scraper(BaseScraper):
    FEED_SLUG     = "test-feed"
    FEED_TITLE    = "Test Feed"
    FEED_SUBTITLE = "A test."
    SOURCE_URL    = "https://example.com/papers/"
    AUTHOR_NAME   = "Test Author"
    AUTHOR_URI    = "https://example.com/"

    def scrape(self) -> list[Paper]:
        return []


_SAMPLE_PAPER = Paper(
    title="A Remarkable Discovery",
    authors="Smith J., Doe A.",
    year=2024,
    pdf_url="https://example.com/paper.pdf",
    journal="Nature",
    volume="123(4): 56-78",
    doi="10.1038/example",
    month=3,
    abstract="This study demonstrates something important.",
)


# ---------------------------------------------------------------------------
# Paper dataclass
# ---------------------------------------------------------------------------

class TestPaper:
    def test_entry_id_is_stable(self):
        p1 = Paper(title="Same Title", authors="A", year=2024, pdf_url="")
        p2 = Paper(title="Same Title", authors="B", year=2024, pdf_url="")
        assert p1.entry_id == p2.entry_id  # ID depends only on title+year

    def test_entry_id_changes_on_different_title(self):
        p1 = Paper(title="Title One", authors="A", year=2024, pdf_url="")
        p2 = Paper(title="Title Two", authors="A", year=2024, pdf_url="")
        assert p1.entry_id != p2.entry_id

    def test_entry_id_format(self):
        p = Paper(title="X", authors="A", year=2022, pdf_url="")
        assert p.entry_id.startswith("tag:atom-feeds,2022:paper/")

    def test_doi_url_with_doi(self):
        p = Paper(title="T", authors="A", year=2024, pdf_url="", doi="10.1038/ex")
        assert p.doi_url == "https://doi.org/10.1038/ex"

    def test_doi_url_without_doi(self):
        p = Paper(title="T", authors="A", year=2024, pdf_url="")
        assert p.doi_url == ""

    def test_published_date_uses_month(self):
        p = Paper(title="T", authors="A", year=2024, pdf_url="", month=7)
        assert p.published_date == "2024-07-01T00:00:00Z"

    def test_published_date_defaults_to_january(self):
        p = Paper(title="T", authors="A", year=2024, pdf_url="")
        assert p.published_date == "2024-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# BaseScraper._self_link
# ---------------------------------------------------------------------------

class TestSelfLink:
    def test_fallback_without_env_var(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        scraper = _Scraper()
        link = scraper._self_link()
        assert "YOUR_GITHUB_USERNAME" in link
        assert "test-feed.atom" in link

    def test_uses_github_repository_env_var(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "alice/atom-feeds")
        scraper = _Scraper()
        link = scraper._self_link()
        assert "alice/atom-feeds" in link
        assert "test-feed.atom" in link
        assert "YOUR_GITHUB_USERNAME" not in link


# ---------------------------------------------------------------------------
# BaseScraper._check_html_cache
# ---------------------------------------------------------------------------

class TestHtmlCache:
    def test_returns_false_with_no_cache_dir(self):
        scraper = _Scraper()
        scraper._cache_dir = None
        assert scraper._check_html_cache("<html/>") is False

    def test_first_call_returns_false_and_writes_hash(self, tmp_path):
        scraper = _Scraper()
        scraper._cache_dir = tmp_path
        result = scraper._check_html_cache("<html>hello</html>")
        assert result is False
        assert (tmp_path / "test-feed.sha256").exists()

    def test_same_content_returns_true(self, tmp_path):
        scraper = _Scraper()
        scraper._cache_dir = tmp_path
        html = "<html>hello</html>"
        scraper._check_html_cache(html)
        assert scraper._check_html_cache(html) is True

    def test_changed_content_returns_false(self, tmp_path):
        scraper = _Scraper()
        scraper._cache_dir = tmp_path
        scraper._check_html_cache("<html>old</html>")
        assert scraper._check_html_cache("<html>new</html>") is False

    def test_cache_dir_created_if_missing(self, tmp_path):
        scraper = _Scraper()
        scraper._cache_dir = tmp_path / "sub" / "cache"
        scraper._check_html_cache("<html/>")
        assert scraper._cache_dir.exists()


# ---------------------------------------------------------------------------
# BaseScraper._build_feed
# ---------------------------------------------------------------------------

class TestBuildFeed:
    def test_output_is_valid_xml_structure(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        scraper = _Scraper()
        xml = scraper._build_feed([_SAMPLE_PAPER])
        assert xml.startswith('<?xml version="1.0"')
        assert '<feed xmlns="http://www.w3.org/2005/Atom"' in xml
        assert '</feed>' in xml

    def test_feed_contains_entry(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        scraper = _Scraper()
        xml = scraper._build_feed([_SAMPLE_PAPER])
        assert '<entry>' in xml
        assert 'A Remarkable Discovery' in xml

    def test_self_link_uses_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "bob/atom-feeds")
        scraper = _Scraper()
        xml = scraper._build_feed([])
        assert "bob/atom-feeds" in xml

    def test_author_is_single_element(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        scraper = _Scraper()
        xml = scraper._build_feed([_SAMPLE_PAPER])
        # The full author string must appear in one <author> block, not split
        assert "<author><name>Smith J., Doe A.</name></author>" in xml

    def test_empty_feed(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        scraper = _Scraper()
        xml = scraper._build_feed([])
        assert '<entry>' not in xml


# ---------------------------------------------------------------------------
# BaseScraper._build_summary
# ---------------------------------------------------------------------------

class TestBuildSummary:
    def test_includes_title(self):
        scraper = _Scraper()
        summary = scraper._build_summary(_SAMPLE_PAPER)
        assert "A Remarkable Discovery" in summary

    def test_includes_doi_link(self):
        scraper = _Scraper()
        summary = scraper._build_summary(_SAMPLE_PAPER)
        assert "10.1038/example" in summary

    def test_includes_abstract(self):
        scraper = _Scraper()
        summary = scraper._build_summary(_SAMPLE_PAPER)
        assert "something important" in summary

    def test_no_abstract_omits_paragraph(self):
        scraper = _Scraper()
        p = Paper(title="T", authors="A", year=2024, pdf_url="", doi="10.1/x")
        summary = scraper._build_summary(p)
        assert "&lt;p&gt;" not in summary


# ---------------------------------------------------------------------------
# BaseScraper.write_feed -- cache-hit path
# ---------------------------------------------------------------------------

class TestWriteFeedCacheHit:
    def test_write_feed_catches_cachehit(self, tmp_path):
        class _CachingAlwaysScraper(_Scraper):
            def scrape(self):
                raise CacheHit()

        scraper = _CachingAlwaysScraper()
        # Should not raise; returns path without writing
        result = scraper.write_feed(tmp_path)
        assert result == tmp_path / "test-feed.atom"
        assert not result.exists()  # file was never written
