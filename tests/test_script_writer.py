"""
TDD tests for pipeline.script_writer
Ollama HTTP calls are fully mocked – no local LLM required.
"""

import unittest
from unittest.mock import patch, MagicMock
import json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_ARTICLE = {
    "title": "OpenAI releases GPT-5",
    "source": "TechCrunch",
    "summary": "OpenAI has released GPT-5, a major leap in AI.",
    "full_text": (
        "OpenAI today announced GPT-5, its most capable language model yet. "
        "The model shows dramatic improvements in reasoning and coding tasks. "
        "It will be available via API immediately. Pricing starts at $0.01 per token. "
        "Safety researchers say the model passed new alignment evaluations. "
        "Competitors are scrambling to respond."
    ),
    "url": "https://techcrunch.com/gpt5",
}

# A script that meets all validation rules (≥80 words, first sentence ≤ 8 words)
VALID_SCRIPT = (
    "AI just changed everything overnight. "
    "OpenAI dropped GPT-5 and it is stunning. "
    "The new model crushes every single benchmark out there. "
    "Coding abilities improved by over three hundred percent easily. "
    "Reasoning tasks that stumped older models now feel trivial. "
    "Safety researchers confirmed it passed the latest alignment tests. "
    "Pricing starts extremely low but will not stay that way. "
    "Google and Meta are already scrambling hard to keep up. "
    "Enterprise customers are signing deals worth billions this very week. "
    "This may be the moment AI became genuinely unstoppable. "
    "Or the moment we finally lost control of our future."
)

def _mock_ollama_response(text: str) -> MagicMock:
    """
    Return a mock requests.Response that streams a single JSON line.
    Each call to iter_lines() returns a fresh iterator so the mock is
    not exhausted after the first use.
    """
    resp = MagicMock()
    resp.status_code = 200
    encoded_line = json.dumps({"response": text, "done": True}).encode()
    resp.iter_lines.side_effect = lambda: iter([encoded_line])
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateScriptSignature(unittest.TestCase):

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_returns_string(self, mock_post):
        from pipeline.script_writer import generate_script

        result = generate_script(SAMPLE_ARTICLE)
        self.assertIsInstance(result, str)

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_result_not_empty(self, mock_post):
        from pipeline.script_writer import generate_script

        result = generate_script(SAMPLE_ARTICLE)
        self.assertGreater(len(result.strip()), 0)

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_ollama_called_with_correct_url(self, mock_post):
        from pipeline.script_writer import generate_script
        import config

        generate_script(SAMPLE_ARTICLE)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], config.OLLAMA_URL)

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_prompt_contains_article_text(self, mock_post):
        from pipeline.script_writer import generate_script

        generate_script(SAMPLE_ARTICLE)
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or kwargs.get("data")
        if isinstance(payload, (bytes, str)):
            payload = json.loads(payload)
        prompt = payload["prompt"]
        self.assertIn(SAMPLE_ARTICLE["full_text"], prompt)

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_model_name_in_payload(self, mock_post):
        from pipeline.script_writer import generate_script
        import config

        generate_script(SAMPLE_ARTICLE)
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or kwargs.get("data")
        if isinstance(payload, (bytes, str)):
            payload = json.loads(payload)
        self.assertEqual(payload["model"], config.OLLAMA_MODEL)


class TestScriptValidation(unittest.TestCase):

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_valid_script_passes_validation(self, mock_post):
        from pipeline.script_writer import generate_script

        result = generate_script(SAMPLE_ARTICLE)
        word_count = len(result.split())
        self.assertGreaterEqual(word_count, 80)
        self.assertLessEqual(word_count, 180)

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_first_sentence_max_8_words(self, mock_post):
        from pipeline.script_writer import generate_script

        result = generate_script(SAMPLE_ARTICLE)
        first_sentence = result.split(".")[0].strip()
        self.assertLessEqual(len(first_sentence.split()), 8)

    def test_too_short_script_triggers_retry(self):
        """Script under 80 words should cause a retry."""
        from pipeline.script_writer import generate_script

        short_script = "This is too short."  # < 80 words
        with patch("pipeline.script_writer.requests.post") as mock_post:
            # Return short script twice then valid on third call
            mock_post.side_effect = [
                _mock_ollama_response(short_script),
                _mock_ollama_response(short_script),
                _mock_ollama_response(VALID_SCRIPT),
            ]
            result = generate_script(SAMPLE_ARTICLE)
            self.assertEqual(mock_post.call_count, 3)
            self.assertGreaterEqual(len(result.split()), 80)

    def test_too_long_script_triggers_retry(self):
        """Script over 180 words should cause a retry."""
        from pipeline.script_writer import generate_script

        long_script = " ".join(["word"] * 200)  # 200 words
        with patch("pipeline.script_writer.requests.post") as mock_post:
            mock_post.side_effect = [
                _mock_ollama_response(long_script),
                _mock_ollama_response(VALID_SCRIPT),
            ]
            result = generate_script(SAMPLE_ARTICLE)
            self.assertEqual(mock_post.call_count, 2)

    def test_raises_after_max_retries_exceeded(self):
        """If all retries produce invalid scripts, ScriptGenerationError is raised."""
        from pipeline.script_writer import generate_script, ScriptGenerationError

        short = "Too short."
        with patch("pipeline.script_writer.requests.post",
                   return_value=_mock_ollama_response(short)):
            with self.assertRaises(ScriptGenerationError):
                generate_script(SAMPLE_ARTICLE)

    def test_hook_too_long_triggers_retry(self):
        """First sentence > 8 words should trigger retry."""
        from pipeline.script_writer import generate_script

        long_hook_script = (
            "This opening sentence is way too long for a hook and breaks the rules. "
            + " ".join(["Valid sentence here."] * 15)
        )
        with patch("pipeline.script_writer.requests.post") as mock_post:
            mock_post.side_effect = [
                _mock_ollama_response(long_hook_script),
                _mock_ollama_response(VALID_SCRIPT),
            ]
            generate_script(SAMPLE_ARTICLE)
            self.assertEqual(mock_post.call_count, 2)


class TestPromptTemplate(unittest.TestCase):

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_prompt_contains_rules_section(self, mock_post):
        from pipeline.script_writer import generate_script

        generate_script(SAMPLE_ARTICLE)
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or {}
        prompt = payload.get("prompt", "")
        self.assertIn("Rules:", prompt)

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_prompt_contains_hook_instruction(self, mock_post):
        from pipeline.script_writer import generate_script

        generate_script(SAMPLE_ARTICLE)
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or {}
        prompt = payload.get("prompt", "")
        self.assertIn("hook", prompt.lower())

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_no_hashtags_instruction_in_prompt(self, mock_post):
        from pipeline.script_writer import generate_script

        generate_script(SAMPLE_ARTICLE)
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or {}
        prompt = payload.get("prompt", "")
        self.assertIn("No hashtags", prompt)


class TestOllamaErrorHandling(unittest.TestCase):

    def test_network_error_raises_script_generation_error(self):
        from pipeline.script_writer import generate_script, ScriptGenerationError
        import requests as req_lib

        with patch("pipeline.script_writer.requests.post",
                   side_effect=req_lib.exceptions.ConnectionError("refused")):
            with self.assertRaises(ScriptGenerationError):
                generate_script(SAMPLE_ARTICLE)

    def test_non_200_response_raises_script_generation_error(self):
        from pipeline.script_writer import generate_script, ScriptGenerationError

        bad_resp = MagicMock()
        bad_resp.status_code = 500
        bad_resp.iter_lines.return_value = iter([])

        with patch("pipeline.script_writer.requests.post", return_value=bad_resp):
            with self.assertRaises(ScriptGenerationError):
                generate_script(SAMPLE_ARTICLE)

    def test_empty_ollama_response_raises_error(self):
        from pipeline.script_writer import generate_script, ScriptGenerationError

        resp = MagicMock()
        resp.status_code = 200
        resp.iter_lines.return_value = iter([])

        with patch("pipeline.script_writer.requests.post", return_value=resp):
            with self.assertRaises(ScriptGenerationError):
                generate_script(SAMPLE_ARTICLE)


class TestBackendParameter(unittest.TestCase):

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_default_backend_is_ollama(self, mock_post):
        from pipeline.script_writer import generate_script

        generate_script(SAMPLE_ARTICLE)  # no backend kwarg
        mock_post.assert_called_once()

    def test_unknown_backend_raises_value_error(self):
        from pipeline.script_writer import generate_script

        with self.assertRaises(ValueError):
            generate_script(SAMPLE_ARTICLE, backend="unknown_backend")


class TestArticleInputEdgeCases(unittest.TestCase):

    @patch("pipeline.script_writer.requests.post", return_value=_mock_ollama_response(VALID_SCRIPT))
    def test_falls_back_to_summary_when_full_text_empty(self, mock_post):
        from pipeline.script_writer import generate_script

        article = dict(SAMPLE_ARTICLE)
        article["full_text"] = ""
        generate_script(article)

        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or {}
        prompt = payload.get("prompt", "")
        self.assertIn(article["summary"], prompt)

    def test_missing_article_keys_raises_value_error(self):
        from pipeline.script_writer import generate_script

        with self.assertRaises((ValueError, KeyError)):
            generate_script({})  # empty dict – required keys missing


if __name__ == "__main__":
    unittest.main()
