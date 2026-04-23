"""
TDD tests for pipeline.tts_engine
Coqui TTS and piper-tts are fully mocked – no GPU / model download required.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call


SAMPLE_SCRIPT = (
    "AI just changed everything overnight. "
    "OpenAI released GPT-5 and it is incredible. "
    "Every benchmark has been shattered completely. "
    "Competitors are already scrambling to catch up."
)


class TestGenerateVoiceoverSignature(unittest.TestCase):

    @patch("pipeline.tts_engine._synthesize_coqui")
    def test_returns_output_path_string(self, mock_synth):
        from pipeline.tts_engine import generate_voiceover

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        mock_synth.return_value = tmp_path
        result = generate_voiceover(SAMPLE_SCRIPT, tmp_path, engine="coqui")

        self.assertIsInstance(result, str)
        os.unlink(tmp_path)

    @patch("pipeline.tts_engine._synthesize_coqui")
    def test_returned_path_equals_output_path(self, mock_synth):
        from pipeline.tts_engine import generate_voiceover

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        mock_synth.return_value = tmp_path
        result = generate_voiceover(SAMPLE_SCRIPT, tmp_path, engine="coqui")
        self.assertEqual(result, tmp_path)
        os.unlink(tmp_path)


class TestCoquiEngine(unittest.TestCase):

    @patch("pipeline.tts_engine._synthesize_coqui")
    def test_coqui_synthesizer_called_with_script_and_path(self, mock_synth):
        from pipeline.tts_engine import generate_voiceover

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        mock_synth.return_value = tmp_path
        generate_voiceover(SAMPLE_SCRIPT, tmp_path, engine="coqui")
        mock_synth.assert_called_once_with(SAMPLE_SCRIPT, tmp_path)
        os.unlink(tmp_path)

    @patch("pipeline.tts_engine.TTS")
    def test_synthesize_coqui_uses_xtts_v2_model(self, MockTTS):
        from pipeline.tts_engine import _synthesize_coqui

        instance = MockTTS.return_value
        instance.tts_to_file = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        _synthesize_coqui(SAMPLE_SCRIPT, tmp_path)

        init_args = MockTTS.call_args
        model_name = init_args[0][0] if init_args[0] else init_args[1].get("model_name", "")
        self.assertIn("xtts", model_name.lower())
        os.unlink(tmp_path)

    @patch("pipeline.tts_engine.TTS")
    def test_synthesize_coqui_calls_tts_to_file(self, MockTTS):
        from pipeline.tts_engine import _synthesize_coqui

        instance = MockTTS.return_value
        instance.tts_to_file = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        _synthesize_coqui(SAMPLE_SCRIPT, tmp_path)
        instance.tts_to_file.assert_called_once()
        os.unlink(tmp_path)

    @patch("pipeline.tts_engine.TTS")
    def test_synthesize_coqui_output_is_wav(self, MockTTS):
        from pipeline.tts_engine import _synthesize_coqui

        instance = MockTTS.return_value
        instance.tts_to_file = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        result = _synthesize_coqui(SAMPLE_SCRIPT, tmp_path)
        self.assertTrue(result.endswith(".wav"))
        os.unlink(tmp_path)


class TestPiperEngine(unittest.TestCase):

    @patch("pipeline.tts_engine._synthesize_piper")
    def test_piper_engine_selected_when_requested(self, mock_piper):
        from pipeline.tts_engine import generate_voiceover

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        mock_piper.return_value = tmp_path
        generate_voiceover(SAMPLE_SCRIPT, tmp_path, engine="piper")
        mock_piper.assert_called_once_with(SAMPLE_SCRIPT, tmp_path)
        os.unlink(tmp_path)

    @patch("pipeline.tts_engine.subprocess")
    def test_synthesize_piper_calls_subprocess(self, mock_subprocess):
        from pipeline.tts_engine import _synthesize_piper

        mock_subprocess.run = MagicMock(return_value=MagicMock(returncode=0))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        _synthesize_piper(SAMPLE_SCRIPT, tmp_path)
        mock_subprocess.run.assert_called_once()
        os.unlink(tmp_path)

    @patch("pipeline.tts_engine.subprocess")
    def test_piper_raises_on_nonzero_returncode(self, mock_subprocess):
        from pipeline.tts_engine import _synthesize_piper, TTSError

        mock_subprocess.run = MagicMock(return_value=MagicMock(returncode=1, stderr=b"error"))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            with self.assertRaises(TTSError):
                _synthesize_piper(SAMPLE_SCRIPT, tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestEngineSelection(unittest.TestCase):

    def test_unknown_engine_raises_value_error(self):
        from pipeline.tts_engine import generate_voiceover

        with self.assertRaises(ValueError):
            generate_voiceover(SAMPLE_SCRIPT, "/tmp/out.wav", engine="unknown")

    @patch("pipeline.tts_engine._synthesize_coqui")
    def test_default_engine_is_coqui(self, mock_coqui):
        from pipeline.tts_engine import generate_voiceover
        import config

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        mock_coqui.return_value = tmp_path
        generate_voiceover(SAMPLE_SCRIPT, tmp_path)  # no engine kwarg
        mock_coqui.assert_called_once()
        os.unlink(tmp_path)


class TestCoquiErrorHandling(unittest.TestCase):

    @patch("pipeline.tts_engine.TTS")
    def test_tts_import_error_raises_tts_error(self, MockTTS):
        from pipeline.tts_engine import _synthesize_coqui, TTSError

        MockTTS.side_effect = Exception("CUDA out of memory")

        with self.assertRaises(TTSError):
            _synthesize_coqui(SAMPLE_SCRIPT, "/tmp/out.wav")

    @patch("pipeline.tts_engine._synthesize_coqui", side_effect=Exception("synthesis failed"))
    def test_generate_voiceover_wraps_exception_as_tts_error(self, mock_synth):
        from pipeline.tts_engine import generate_voiceover, TTSError

        with self.assertRaises(TTSError):
            generate_voiceover(SAMPLE_SCRIPT, "/tmp/out.wav", engine="coqui")


class TestInputValidation(unittest.TestCase):

    def test_empty_script_raises_value_error(self):
        from pipeline.tts_engine import generate_voiceover

        with self.assertRaises(ValueError):
            generate_voiceover("", "/tmp/out.wav")

    def test_none_script_raises_value_error(self):
        from pipeline.tts_engine import generate_voiceover

        with self.assertRaises((ValueError, TypeError)):
            generate_voiceover(None, "/tmp/out.wav")

    def test_empty_output_path_raises_value_error(self):
        from pipeline.tts_engine import generate_voiceover

        with self.assertRaises(ValueError):
            generate_voiceover(SAMPLE_SCRIPT, "")


if __name__ == "__main__":
    unittest.main()
