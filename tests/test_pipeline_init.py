"""
Tests that pipeline/__init__.py lazy wrapper functions delegate correctly
to their underlying module implementations.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestPipelineInitDelegation(unittest.TestCase):
    """Each wrapper in pipeline/__init__.py must forward to the real function."""

    @patch("pipeline.news_fetcher.fetch_latest_news")
    def test_fetch_latest_news_delegates(self, mock_fn):
        import pipeline
        mock_fn.return_value = {"title": "x", "source": "y", "summary": "z",
                                "full_text": "body", "url": "u"}
        result = pipeline.fetch_latest_news(feed_urls=["https://fake/rss"])
        mock_fn.assert_called_once_with(feed_urls=["https://fake/rss"])
        self.assertEqual(result["title"], "x")

    @patch("pipeline.script_writer.generate_script")
    def test_generate_script_delegates(self, mock_fn):
        import pipeline
        mock_fn.return_value = "Great script here."
        article = {"title": "t", "summary": "s", "full_text": "f", "url": "u", "source": "src"}
        result = pipeline.generate_script(article, backend="ollama")
        mock_fn.assert_called_once_with(article, backend="ollama")
        self.assertEqual(result, "Great script here.")

    @patch("pipeline.tts_engine.generate_voiceover")
    def test_generate_voiceover_delegates(self, mock_fn):
        import pipeline
        mock_fn.return_value = "/tmp/out.wav"
        result = pipeline.generate_voiceover("script text", "/tmp/out.wav", engine="coqui")
        mock_fn.assert_called_once_with("script text", "/tmp/out.wav", engine="coqui")
        self.assertEqual(result, "/tmp/out.wav")

    @patch("pipeline.caption_sync.extract_word_timestamps")
    def test_extract_word_timestamps_delegates(self, mock_fn):
        import pipeline
        mock_fn.return_value = [{"word": "hi", "start": 0.0, "end": 0.3}]
        result = pipeline.extract_word_timestamps("/fake/audio.wav")
        mock_fn.assert_called_once_with("/fake/audio.wav")
        self.assertEqual(len(result), 1)

    @patch("pipeline.caption_sync.group_into_caption_chunks")
    def test_group_into_caption_chunks_delegates(self, mock_fn):
        import pipeline
        words = [{"word": "hi", "start": 0.0, "end": 0.3}]
        mock_fn.return_value = [{"text": "hi", "start_time": 0.0, "end_time": 0.3}]
        result = pipeline.group_into_caption_chunks(words, chunk_size=4)
        mock_fn.assert_called_once_with(words, chunk_size=4)
        self.assertEqual(len(result), 1)

    @patch("pipeline.video_composer.compose_video")
    def test_compose_video_delegates(self, mock_fn):
        import pipeline
        mock_fn.return_value = "/fake/out.mp4"
        captions = [{"text": "hi", "start_time": 0.0, "end_time": 1.0}]
        result = pipeline.compose_video("/fake/bg.mp4", "/fake/audio.wav",
                                        captions, "/fake/out.mp4")
        mock_fn.assert_called_once()
        self.assertEqual(result, "/fake/out.mp4")

    @patch("pipeline.background_source.get_background_video")
    def test_get_background_video_delegates(self, mock_fn):
        import pipeline
        mock_fn.return_value = "/fake/bg.mp4"
        result = pipeline.get_background_video(30.0, category="tech")
        mock_fn.assert_called_once_with(30.0, category="tech")
        self.assertEqual(result, "/fake/bg.mp4")


if __name__ == "__main__":
    unittest.main()
