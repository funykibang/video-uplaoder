"""
TDD tests for pipeline.news_fetcher
All external I/O (feedparser, newspaper3k, trafilatura, sqlite3) is mocked.
"""

import sqlite3
import unittest
from unittest.mock import MagicMock, patch, call
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feed_entry(title="Test Title", link="https://example.com/1",
                     summary="Short summary.", published="Mon, 20 Apr 2026 10:00:00 +0000"):
    """Return a fake feedparser entry object."""
    entry = SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
        published=published,
    )
    return entry


def _make_feed(entries=None, bozo=False):
    """Return a fake feedparser result."""
    feed = SimpleNamespace(
        bozo=bozo,
        entries=[_make_feed_entry()] if entries is None else entries,
    )
    return feed


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestFetchLatestNewsSignature(unittest.TestCase):
    """fetch_latest_news must return a dict with the required keys."""

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Full article body text here.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed())
    def test_returns_dict_with_required_keys(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news

        result = fetch_latest_news(feed_urls=["https://fake.feed/rss"])

        self.assertIsInstance(result, dict)
        for key in ("title", "source", "summary", "full_text", "url"):
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Full article body text here.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed())
    def test_title_matches_feed_entry(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news

        result = fetch_latest_news(feed_urls=["https://fake.feed/rss"])
        self.assertEqual(result["title"], "Test Title")

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Full article body text here.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed())
    def test_url_matches_feed_entry(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news

        result = fetch_latest_news(feed_urls=["https://fake.feed/rss"])
        self.assertEqual(result["url"], "https://example.com/1")

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body text.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed())
    def test_full_text_comes_from_helper(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news

        result = fetch_latest_news(feed_urls=["https://fake.feed/rss"])
        self.assertEqual(result["full_text"], "Body text.")

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body text.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed())
    def test_uses_default_rss_feeds_when_none_provided(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news
        import config

        fetch_latest_news()  # no feed_urls argument
        # feedparser.parse must be called with one of the default RSS feed URLs
        mock_parse.assert_called()
        called_url = mock_parse.call_args[0][0]
        self.assertIn(called_url, config.RSS_FEEDS)


class TestDeduplicate(unittest.TestCase):
    """Articles already seen must be skipped; unseen ones are marked."""

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body.")
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("pipeline.news_fetcher._is_seen")
    @patch("feedparser.parse")
    def test_skips_seen_articles_moves_to_next(self, mock_parse, mock_seen, mock_mark, mock_full):
        """First entry is seen, second is not – should return second entry."""
        from pipeline.news_fetcher import fetch_latest_news

        entry1 = _make_feed_entry(title="Old News", link="https://example.com/old")
        entry2 = _make_feed_entry(title="Fresh News", link="https://example.com/new")
        mock_parse.return_value = _make_feed(entries=[entry1, entry2])
        mock_seen.side_effect = [True, False]  # first seen, second not

        result = fetch_latest_news(feed_urls=["https://fake.feed/rss"])
        self.assertEqual(result["title"], "Fresh News")

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body.")
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("feedparser.parse", return_value=_make_feed())
    def test_marks_article_as_seen_after_selection(self, mock_parse, mock_seen, mock_mark, mock_full):
        from pipeline.news_fetcher import fetch_latest_news

        fetch_latest_news(feed_urls=["https://fake.feed/rss"])
        mock_mark.assert_called_once()

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body.")
    @patch("pipeline.news_fetcher._is_seen", return_value=True)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed(entries=[
        _make_feed_entry(title="All Seen", link="https://example.com/seen")
    ]))
    def test_raises_when_all_articles_seen(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news, NoNewArticlesError

        with self.assertRaises(NoNewArticlesError):
            fetch_latest_news(feed_urls=["https://fake.feed/rss"])


class TestFetchFullText(unittest.TestCase):
    """_fetch_full_text tries newspaper3k then falls back to trafilatura."""

    @patch("pipeline.news_fetcher.trafilatura")
    @patch("pipeline.news_fetcher.Article")
    def test_returns_newspaper_text_when_available(self, MockArticle, mock_traf):
        from pipeline.news_fetcher import _fetch_full_text

        instance = MockArticle.return_value
        instance.text = "Newspaper article text."
        result = _fetch_full_text("https://example.com/1")

        self.assertEqual(result, "Newspaper article text.")

    @patch("pipeline.news_fetcher.trafilatura")
    @patch("pipeline.news_fetcher.Article")
    def test_falls_back_to_trafilatura_on_empty_newspaper(self, MockArticle, mock_traf):
        from pipeline.news_fetcher import _fetch_full_text

        instance = MockArticle.return_value
        instance.text = ""  # newspaper returned nothing
        mock_traf.fetch_url.return_value = "<html>raw</html>"
        mock_traf.extract.return_value = "Trafilatura text."

        result = _fetch_full_text("https://example.com/1")
        self.assertEqual(result, "Trafilatura text.")

    @patch("pipeline.news_fetcher.trafilatura")
    @patch("pipeline.news_fetcher.Article")
    def test_falls_back_to_trafilatura_on_exception(self, MockArticle, mock_traf):
        from pipeline.news_fetcher import _fetch_full_text

        MockArticle.side_effect = Exception("network error")
        mock_traf.fetch_url.return_value = "<html>raw</html>"
        mock_traf.extract.return_value = "Trafilatura fallback."

        result = _fetch_full_text("https://example.com/1")
        self.assertEqual(result, "Trafilatura fallback.")

    @patch("pipeline.news_fetcher.trafilatura")
    @patch("pipeline.news_fetcher.Article")
    def test_returns_empty_string_when_both_fail(self, MockArticle, mock_traf):
        from pipeline.news_fetcher import _fetch_full_text

        MockArticle.side_effect = Exception("fail")
        mock_traf.fetch_url.return_value = None
        mock_traf.extract.return_value = None

        result = _fetch_full_text("https://example.com/1")
        self.assertEqual(result, "")


class TestIsSeenMarkSeen(unittest.TestCase):
    """_is_seen and _mark_seen interact with SQLite in-memory DB."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE seen_articles (url TEXT PRIMARY KEY, seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    @patch("pipeline.news_fetcher._get_db_conn")
    def test_is_seen_returns_false_for_new_url(self, mock_conn):
        from pipeline.news_fetcher import _is_seen

        mock_conn.return_value = self.conn
        self.assertFalse(_is_seen("https://example.com/new"))

    @patch("pipeline.news_fetcher._get_db_conn")
    def test_is_seen_returns_true_after_mark(self, mock_conn):
        from pipeline.news_fetcher import _is_seen, _mark_seen

        mock_conn.return_value = self.conn
        _mark_seen("https://example.com/article")
        self.assertTrue(_is_seen("https://example.com/article"))

    @patch("pipeline.news_fetcher._get_db_conn")
    def test_mark_seen_is_idempotent(self, mock_conn):
        from pipeline.news_fetcher import _mark_seen

        mock_conn.return_value = self.conn
        _mark_seen("https://example.com/dup")
        _mark_seen("https://example.com/dup")  # should not raise


class TestFeedParsing(unittest.TestCase):
    """Feed-level edge cases."""

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse")
    def test_bozo_feed_is_skipped_gracefully(self, mock_parse, mock_mark, mock_seen, mock_full):
        """Malformed (bozo) feeds should be skipped; function falls through to next feed."""
        from pipeline.news_fetcher import fetch_latest_news

        good_entry = _make_feed_entry(title="Good News", link="https://good.com/1")
        mock_parse.side_effect = [
            _make_feed(bozo=True, entries=[]),           # first feed malformed
            _make_feed(bozo=False, entries=[good_entry]),# second feed ok
        ]

        result = fetch_latest_news(feed_urls=["https://bad.feed/", "https://good.feed/"])
        self.assertEqual(result["title"], "Good News")

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", return_value=_make_feed(entries=[]))
    def test_raises_when_all_feeds_empty(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news, NoNewArticlesError

        with self.assertRaises(NoNewArticlesError):
            fetch_latest_news(feed_urls=["https://empty.feed/"])

    @patch("pipeline.news_fetcher._fetch_full_text", return_value="Body.")
    @patch("pipeline.news_fetcher._is_seen", return_value=False)
    @patch("pipeline.news_fetcher._mark_seen")
    @patch("feedparser.parse", side_effect=Exception("connection refused"))
    def test_raises_on_network_error(self, mock_parse, mock_mark, mock_seen, mock_full):
        from pipeline.news_fetcher import fetch_latest_news, NoNewArticlesError

        with self.assertRaises(NoNewArticlesError):
            fetch_latest_news(feed_urls=["https://unreachable.feed/"])


if __name__ == "__main__":
    unittest.main()
