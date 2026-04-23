"""
TDD tests for pipeline.caption_sync
faster-whisper is fully mocked – no model download or GPU required.
"""

import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers – fake faster-whisper objects
# ---------------------------------------------------------------------------

def _make_word(word: str, start: float, end: float):
    return SimpleNamespace(word=word, start=start, end=end)


def _make_segment(words):
    return SimpleNamespace(words=words)


def _make_whisper_result(segments):
    """Returns (segments_iterable, info) matching faster-whisper's API."""
    return iter(segments), SimpleNamespace(language="en", language_probability=0.99)


SAMPLE_WORDS = [
    _make_word("AI",       0.00, 0.20),
    _make_word("just",     0.22, 0.40),
    _make_word("changed",  0.42, 0.70),
    _make_word("everything", 0.72, 1.10),
    _make_word("overnight.", 1.12, 1.60),
    _make_word("OpenAI",   1.80, 2.10),
    _make_word("released", 2.12, 2.50),
    _make_word("GPT-5",    2.52, 2.90),
]

SAMPLE_SEGMENT = _make_segment(SAMPLE_WORDS)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractWordTimestamps(unittest.TestCase):

    @patch("pipeline.caption_sync.WhisperModel")
    def test_returns_list(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([SAMPLE_SEGMENT])

        result = extract_word_timestamps("/fake/audio.wav")
        self.assertIsInstance(result, list)

    @patch("pipeline.caption_sync.WhisperModel")
    def test_each_item_has_required_keys(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([SAMPLE_SEGMENT])

        result = extract_word_timestamps("/fake/audio.wav")
        for item in result:
            for key in ("word", "start", "end"):
                self.assertIn(key, item, f"Missing key '{key}' in {item}")

    @patch("pipeline.caption_sync.WhisperModel")
    def test_word_count_matches_input(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([SAMPLE_SEGMENT])

        result = extract_word_timestamps("/fake/audio.wav")
        self.assertEqual(len(result), len(SAMPLE_WORDS))

    @patch("pipeline.caption_sync.WhisperModel")
    def test_timestamps_are_floats(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([SAMPLE_SEGMENT])

        result = extract_word_timestamps("/fake/audio.wav")
        for item in result:
            self.assertIsInstance(item["start"], float)
            self.assertIsInstance(item["end"], float)

    @patch("pipeline.caption_sync.WhisperModel")
    def test_words_are_stripped_of_whitespace(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        padded_words = [_make_word(" hello ", 0.0, 0.5)]
        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([_make_segment(padded_words)])

        result = extract_word_timestamps("/fake/audio.wav")
        self.assertEqual(result[0]["word"], "hello")

    @patch("pipeline.caption_sync.WhisperModel")
    def test_multiple_segments_are_flattened(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        seg1 = _make_segment([_make_word("Hello", 0.0, 0.3)])
        seg2 = _make_segment([_make_word("world", 0.5, 0.8)])
        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([seg1, seg2])

        result = extract_word_timestamps("/fake/audio.wav")
        self.assertEqual(len(result), 2)

    @patch("pipeline.caption_sync.WhisperModel")
    def test_transcribe_called_with_word_timestamps_true(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([SAMPLE_SEGMENT])

        extract_word_timestamps("/fake/audio.wav")
        _, kwargs = instance.transcribe.call_args
        self.assertTrue(kwargs.get("word_timestamps", False))

    @patch("pipeline.caption_sync.WhisperModel")
    def test_empty_audio_returns_empty_list(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps

        instance = MockWhisper.return_value
        instance.transcribe.return_value = _make_whisper_result([])

        result = extract_word_timestamps("/fake/silence.wav")
        self.assertEqual(result, [])


class TestGroupIntoCaptionChunks(unittest.TestCase):

    def _sample_words(self):
        return [
            {"word": "AI",          "start": 0.00, "end": 0.20},
            {"word": "just",        "start": 0.22, "end": 0.40},
            {"word": "changed",     "start": 0.42, "end": 0.70},
            {"word": "everything",  "start": 0.72, "end": 1.10},
            {"word": "overnight",   "start": 1.12, "end": 1.60},
            {"word": "OpenAI",      "start": 1.80, "end": 2.10},
            {"word": "released",    "start": 2.12, "end": 2.50},
            {"word": "GPT-5",       "start": 2.52, "end": 2.90},
        ]

    def test_returns_list(self):
        from pipeline.caption_sync import group_into_caption_chunks

        result = group_into_caption_chunks(self._sample_words())
        self.assertIsInstance(result, list)

    def test_each_chunk_has_required_keys(self):
        from pipeline.caption_sync import group_into_caption_chunks

        result = group_into_caption_chunks(self._sample_words())
        for chunk in result:
            for key in ("text", "start_time", "end_time"):
                self.assertIn(key, chunk)

    def test_default_chunk_size_is_4(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()  # 8 words → 2 chunks of 4
        result = group_into_caption_chunks(words)
        self.assertEqual(len(result), 2)

    def test_custom_chunk_size(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()  # 8 words, chunk_size=2 → 4 chunks
        result = group_into_caption_chunks(words, chunk_size=2)
        self.assertEqual(len(result), 4)

    def test_chunk_text_joins_words(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()
        result = group_into_caption_chunks(words, chunk_size=4)
        self.assertEqual(result[0]["text"], "AI just changed everything")

    def test_chunk_start_time_is_first_word_start(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()
        result = group_into_caption_chunks(words)
        self.assertAlmostEqual(result[0]["start_time"], 0.00)

    def test_chunk_end_time_is_last_word_end(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()
        result = group_into_caption_chunks(words)
        self.assertAlmostEqual(result[0]["end_time"], 1.10)

    def test_last_chunk_smaller_than_chunk_size(self):
        from pipeline.caption_sync import group_into_caption_chunks

        # 5 words with chunk_size=4 → chunks of 4 and 1
        words = self._sample_words()[:5]
        result = group_into_caption_chunks(words, chunk_size=4)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["text"], "overnight")

    def test_empty_words_returns_empty_list(self):
        from pipeline.caption_sync import group_into_caption_chunks

        result = group_into_caption_chunks([])
        self.assertEqual(result, [])

    def test_single_word(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
        result = group_into_caption_chunks(words, chunk_size=4)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Hello")

    def test_chunk_size_one(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()[:3]
        result = group_into_caption_chunks(words, chunk_size=1)
        self.assertEqual(len(result), 3)

    def test_chunk_size_larger_than_word_count(self):
        from pipeline.caption_sync import group_into_caption_chunks

        words = self._sample_words()[:3]
        result = group_into_caption_chunks(words, chunk_size=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["text"].split()), 3)


class TestExtractWordTimestampsErrorHandling(unittest.TestCase):

    @patch("pipeline.caption_sync.WhisperModel")
    def test_whisper_exception_raises_caption_error(self, MockWhisper):
        from pipeline.caption_sync import extract_word_timestamps, CaptionSyncError

        instance = MockWhisper.return_value
        instance.transcribe.side_effect = RuntimeError("model load failed")

        with self.assertRaises(CaptionSyncError):
            extract_word_timestamps("/fake/audio.wav")

    def test_invalid_chunk_size_raises_value_error(self):
        from pipeline.caption_sync import group_into_caption_chunks

        with self.assertRaises(ValueError):
            group_into_caption_chunks([{"word": "hi", "start": 0.0, "end": 0.5}], chunk_size=0)

    def test_negative_chunk_size_raises_value_error(self):
        from pipeline.caption_sync import group_into_caption_chunks

        with self.assertRaises(ValueError):
            group_into_caption_chunks([], chunk_size=-1)


if __name__ == "__main__":
    unittest.main()
