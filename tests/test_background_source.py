"""
TDD tests for pipeline.background_source
All filesystem and HTTP operations are mocked.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock


class TestGetBackgroundVideoLocal(unittest.TestCase):

    @patch("pipeline.background_source._list_local_backgrounds")
    def test_returns_string_path(self, mock_list):
        from pipeline.background_source import get_background_video

        mock_list.return_value = ["/fake/assets/backgrounds/clip1.mp4"]
        result = get_background_video(30.0)
        self.assertIsInstance(result, str)

    @patch("pipeline.background_source._list_local_backgrounds")
    def test_returns_one_of_the_local_paths(self, mock_list):
        from pipeline.background_source import get_background_video

        paths = [
            "/fake/assets/backgrounds/clip1.mp4",
            "/fake/assets/backgrounds/clip2.mp4",
        ]
        mock_list.return_value = paths
        result = get_background_video(30.0)
        self.assertIn(result, paths)

    @patch("pipeline.background_source._list_local_backgrounds")
    def test_local_overrides_pexels(self, mock_list):
        """When local files exist, Pexels is never contacted."""
        from pipeline.background_source import get_background_video

        mock_list.return_value = ["/fake/clip.mp4"]
        with patch("pipeline.background_source._download_from_pexels") as mock_dl:
            get_background_video(30.0)
            mock_dl.assert_not_called()


class TestGetBackgroundVideoPexelsFallback(unittest.TestCase):

    @patch("pipeline.background_source._download_from_pexels")
    @patch("pipeline.background_source._list_local_backgrounds", return_value=[])
    def test_falls_back_to_pexels_when_no_local(self, mock_list, mock_dl):
        from pipeline.background_source import get_background_video

        mock_dl.return_value = "/tmp/pexels_video.mp4"
        result = get_background_video(30.0)
        self.assertEqual(result, "/tmp/pexels_video.mp4")
        mock_dl.assert_called_once()

    @patch("pipeline.background_source._download_from_pexels")
    @patch("pipeline.background_source._list_local_backgrounds", return_value=[])
    def test_pexels_called_with_duration_and_category(self, mock_list, mock_dl):
        from pipeline.background_source import get_background_video

        mock_dl.return_value = "/tmp/vid.mp4"
        get_background_video(45.0, category="tech")
        mock_dl.assert_called_once_with(45.0, "tech")

    @patch("pipeline.background_source._download_from_pexels", return_value=None)
    @patch("pipeline.background_source._list_local_backgrounds", return_value=[])
    def test_raises_when_both_sources_fail(self, mock_list, mock_dl):
        from pipeline.background_source import get_background_video, BackgroundSourceError

        with self.assertRaises(BackgroundSourceError):
            get_background_video(30.0)

    @patch("pipeline.background_source._download_from_pexels", return_value=None)
    @patch("pipeline.background_source._list_local_backgrounds", return_value=[])
    def test_error_message_mentions_assets_dir(self, mock_list, mock_dl):
        from pipeline.background_source import get_background_video, BackgroundSourceError

        try:
            get_background_video(30.0)
            self.fail("Expected BackgroundSourceError")
        except BackgroundSourceError as e:
            self.assertIn("backgrounds", str(e).lower())


class TestListLocalBackgrounds(unittest.TestCase):

    def test_returns_list(self):
        from pipeline.background_source import _list_local_backgrounds

        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["a.mp4", "b.mp4", "notes.txt"]):
            result = _list_local_backgrounds()
        self.assertIsInstance(result, list)

    def test_only_returns_mp4_files(self):
        from pipeline.background_source import _list_local_backgrounds

        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["clip.mp4", "readme.txt", "image.jpg", "vid.MP4"]):
            result = _list_local_backgrounds()
        # Only lowercase .mp4 files
        for path in result:
            self.assertTrue(path.endswith(".mp4") or path.endswith(".MP4"))

    def test_returns_empty_when_dir_missing(self):
        from pipeline.background_source import _list_local_backgrounds

        with patch("os.path.isdir", return_value=False):
            result = _list_local_backgrounds()
        self.assertEqual(result, [])

    def test_returns_empty_when_no_mp4s(self):
        from pipeline.background_source import _list_local_backgrounds

        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["readme.txt", "image.png"]):
            result = _list_local_backgrounds()
        self.assertEqual(result, [])


class TestDownloadFromPexels(unittest.TestCase):

    def test_returns_none_when_no_api_key(self):
        from pipeline.background_source import _download_from_pexels
        import config

        original = config.PEXELS_API_KEY
        try:
            config.PEXELS_API_KEY = ""
            result = _download_from_pexels(30.0, "satisfying")
            self.assertIsNone(result)
        finally:
            config.PEXELS_API_KEY = original

    def test_returns_none_on_http_error(self):
        from pipeline.background_source import _download_from_pexels
        import config

        original = config.PEXELS_API_KEY
        try:
            config.PEXELS_API_KEY = "fake-key"
            with patch("pipeline.background_source.requests") as mock_req:
                mock_req.get.side_effect = Exception("Connection refused")
                result = _download_from_pexels(30.0, "satisfying")
            self.assertIsNone(result)
        finally:
            config.PEXELS_API_KEY = original

    def test_returns_none_when_no_videos_in_response(self):
        from pipeline.background_source import _download_from_pexels
        import config

        original = config.PEXELS_API_KEY
        try:
            config.PEXELS_API_KEY = "fake-key"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"videos": []}
            mock_resp.raise_for_status = MagicMock()
            with patch("pipeline.background_source.requests") as mock_req:
                mock_req.get.return_value = mock_resp
                result = _download_from_pexels(30.0, "satisfying")
            self.assertIsNone(result)
        finally:
            config.PEXELS_API_KEY = original

    def test_downloads_video_and_returns_path(self):
        from pipeline.background_source import _download_from_pexels
        import config

        original = config.PEXELS_API_KEY
        try:
            config.PEXELS_API_KEY = "fake-key"

            # Build mock search response
            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {
                "videos": [{
                    "video_files": [
                        {"link": "https://cdn.pexels.com/vid.mp4", "width": 1920}
                    ]
                }]
            }
            # Build mock download response
            dl_resp = MagicMock()
            dl_resp.raise_for_status = MagicMock()
            dl_resp.iter_content.return_value = iter([b"fakedata"])

            with patch("pipeline.background_source.requests") as mock_req, \
                 patch("os.path.isdir", return_value=True), \
                 patch("tempfile.mkstemp") as mock_mkstemp, \
                 patch("os.fdopen") as mock_fdopen:
                mock_req.get.side_effect = [search_resp, dl_resp]
                mock_mkstemp.return_value = (5, "/tmp/bg_1234.mp4")
                mock_fdopen.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_fdopen.return_value.__exit__ = MagicMock(return_value=False)

                result = _download_from_pexels(30.0, "satisfying")

            self.assertEqual(result, "/tmp/bg_1234.mp4")
        finally:
            config.PEXELS_API_KEY = original


class TestDefaultCategory(unittest.TestCase):

    @patch("pipeline.background_source._list_local_backgrounds")
    def test_default_category_is_satisfying(self, mock_list):
        from pipeline.background_source import get_background_video

        mock_list.return_value = ["/fake/clip.mp4"]
        # Just verify it doesn't raise with default category
        result = get_background_video(30.0)  # no category arg
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
