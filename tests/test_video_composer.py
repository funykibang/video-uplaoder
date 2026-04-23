"""
TDD tests for pipeline.video_composer
FFmpeg (ffmpeg-python) is fully mocked – no FFmpeg binary required.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_CAPTIONS = [
    {"text": "AI just changed everything", "start_time": 0.00, "end_time": 1.10},
    {"text": "overnight OpenAI released GPT-5", "start_time": 1.12, "end_time": 2.90},
    {"text": "every benchmark shattered completely", "start_time": 3.00, "end_time": 4.50},
]


# ---------------------------------------------------------------------------
# Tests – compose_video
# ---------------------------------------------------------------------------

class TestComposeVideoSignature(unittest.TestCase):

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_returns_output_path_string(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        mock_ffmpeg.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            out = f.name

        result = compose_video(
            background_path="/fake/bg.mp4",
            audio_path="/fake/audio.wav",
            captions=SAMPLE_CAPTIONS,
            output_path=out,
        )
        self.assertIsInstance(result, str)
        os.unlink(out)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_returned_path_equals_output_path(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        mock_ffmpeg.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            out = f.name

        result = compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, out)
        self.assertEqual(result, out)
        os.unlink(out)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_ffmpeg_called_once(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        mock_ffmpeg.assert_called_once()


class TestComposeVideoParameters(unittest.TestCase):

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_default_resolution_is_1080x1920(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, kwargs = mock_ffmpeg.call_args
        # resolution should appear somewhere in the ffmpeg arguments
        cmd_str = " ".join(str(a) for a in args[0]) if args else str(kwargs)
        self.assertIn("1080", cmd_str)
        self.assertIn("1920", cmd_str)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_custom_resolution_passed_through(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4",
                      resolution=(720, 1280))
        args, kwargs = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0]) if args else str(kwargs)
        self.assertIn("720", cmd_str)
        self.assertIn("1280", cmd_str)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_audio_path_included_in_ffmpeg_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("/fake/audio.wav", cmd_str)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_background_path_included_in_ffmpeg_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("/fake/bg.mp4", cmd_str)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_output_path_included_in_ffmpeg_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("/fake/out.mp4", cmd_str)


class TestASSSubtitleGeneration(unittest.TestCase):

    def test_build_ass_returns_string(self):
        from pipeline.video_composer import _build_ass_subtitles

        result = _build_ass_subtitles(SAMPLE_CAPTIONS)
        self.assertIsInstance(result, str)

    def test_ass_contains_script_info_section(self):
        from pipeline.video_composer import _build_ass_subtitles

        result = _build_ass_subtitles(SAMPLE_CAPTIONS)
        self.assertIn("[Script Info]", result)

    def test_ass_contains_events_section(self):
        from pipeline.video_composer import _build_ass_subtitles

        result = _build_ass_subtitles(SAMPLE_CAPTIONS)
        self.assertIn("[Events]", result)

    def test_ass_contains_dialogue_lines(self):
        from pipeline.video_composer import _build_ass_subtitles

        result = _build_ass_subtitles(SAMPLE_CAPTIONS)
        self.assertIn("Dialogue:", result)

    def test_ass_contains_all_caption_texts(self):
        from pipeline.video_composer import _build_ass_subtitles

        result = _build_ass_subtitles(SAMPLE_CAPTIONS)
        for caption in SAMPLE_CAPTIONS:
            self.assertIn(caption["text"], result)

    def test_ass_timestamps_formatted_correctly(self):
        """ASS timestamps should be H:MM:SS.cc format."""
        from pipeline.video_composer import _format_ass_timestamp

        self.assertEqual(_format_ass_timestamp(0.0),   "0:00:00.00")
        self.assertEqual(_format_ass_timestamp(61.5),  "0:01:01.50")
        self.assertEqual(_format_ass_timestamp(3661.0),"1:01:01.00")

    def test_ass_contains_font_name(self):
        from pipeline.video_composer import _build_ass_subtitles
        import config

        result = _build_ass_subtitles(SAMPLE_CAPTIONS)
        self.assertIn(config.CAPTION_FONT, result)

    def test_empty_captions_produces_valid_ass(self):
        from pipeline.video_composer import _build_ass_subtitles

        result = _build_ass_subtitles([])
        self.assertIn("[Script Info]", result)
        self.assertIn("[Events]", result)


class TestVideoEncodingSettings(unittest.TestCase):

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_crf_18_in_ffmpeg_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("18", cmd_str)  # CRF value

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_aac_audio_codec_in_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("aac", cmd_str)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_192k_audio_bitrate_in_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("192k", cmd_str)

    @patch("pipeline.video_composer._run_ffmpeg")
    def test_30fps_in_args(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video

        compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")
        args, _ = mock_ffmpeg.call_args
        cmd_str = " ".join(str(a) for a in args[0])
        self.assertIn("30", cmd_str)


class TestErrorHandling(unittest.TestCase):

    @patch("pipeline.video_composer._run_ffmpeg", side_effect=RuntimeError("ffmpeg not found"))
    def test_ffmpeg_error_raises_video_composer_error(self, mock_ffmpeg):
        from pipeline.video_composer import compose_video, VideoComposerError

        with self.assertRaises(VideoComposerError):
            compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4")

    def test_empty_captions_list_raises_value_error(self):
        from pipeline.video_composer import compose_video

        with self.assertRaises(ValueError):
            compose_video("/fake/bg.mp4", "/fake/audio.wav", [], "/fake/out.mp4")

    def test_invalid_resolution_tuple_raises_value_error(self):
        from pipeline.video_composer import compose_video

        with self.assertRaises(ValueError):
            compose_video("/fake/bg.mp4", "/fake/audio.wav", SAMPLE_CAPTIONS, "/fake/out.mp4",
                          resolution=(0, 1920))


class TestFormatAssTimestamp(unittest.TestCase):

    def test_zero_seconds(self):
        from pipeline.video_composer import _format_ass_timestamp
        self.assertEqual(_format_ass_timestamp(0), "0:00:00.00")

    def test_90_seconds(self):
        from pipeline.video_composer import _format_ass_timestamp
        self.assertEqual(_format_ass_timestamp(90), "0:01:30.00")

    def test_fractional_seconds(self):
        from pipeline.video_composer import _format_ass_timestamp
        self.assertEqual(_format_ass_timestamp(1.75), "0:00:01.75")

    def test_one_hour(self):
        from pipeline.video_composer import _format_ass_timestamp
        self.assertEqual(_format_ass_timestamp(3600), "1:00:00.00")


if __name__ == "__main__":
    unittest.main()
