"""
pipeline.script_writer
~~~~~~~~~~~~~~~~~~~~~~
Generates a TikTok-style narration script from an article dict using Ollama.

Public API
----------
pick_best_article(candidates: list[dict]) -> dict
generate_script(article: dict, backend="ollama") -> str
"""

import json
import logging
import re
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ScriptGenerationError(RuntimeError):
    """Raised when a valid script cannot be produced within the retry budget."""


# ---------------------------------------------------------------------------
# Prompt template (exact, as specified)
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are writing a viral, funny TikTok dialogue about a tech news story.

CRITICAL GOAL:
The viewer MUST understand the news clearly by the end, even if it's chaotic.

MANDATORY CLARITY LINE:
Within the first 2 lines, explicitly state:
- What happened (in plain English)
- Who it affects
- Why it matters
(do not acctually say "what happened", "who it affects", or "why it matters" — just include that info clearly in the dialogue)

If this is not clear, rewrite until it is.

Characters:
- SCIENTIST: an arrogant, unhinged expert who over-explains everything. Gets increasingly aggressive and takes confusion personally. Uses simple explanations but delivers them like a meltdown. Ends rants with insults like "YOU ARE DUMB", "HOW DO YOU NOT GET THIS", "IT IS SO OBVIOUS BECAUSE—".
- VILLAGER: completely unbothered. Not stupid—just doesn't care. Keeps asking "why should I care" or dismissing everything.

STRUCTURE (VERY IMPORTANT):
1. First line = STRONG HOOK (clear stakes or absurd consequence of the news)
2. Within the FIRST 2–3 lines → clearly explain:
   - What happened
   - Who/what it affects
   - Why it matters
3. Middle lines:
   - SCIENTIST explains WHY it matters (real-world impact, simple terms)
   - Use comparisons, analogies, or everyday examples
4. Escalation:
   - SCIENTIST gets more unhinged each line
   - VILLAGER stays calm and dismissive
5. Final line:
   - VILLAGER says something dismissive that completely kills the energy

CLARITY RULES:
- Avoid jargon unless immediately explained simply
- Every explanation must be understandable to a non-tech person
- If a concept is complex, simplify it aggressively
- Prioritize clarity over cleverness

FORMAT RULES:
- ONLY use: SCIENTIST: <line> or VILLAGER: <line>
- 8–12 alternating lines
- SCIENTIST lines: up to 25 words — let him explain, rant, spiral
- VILLAGER lines: max 10 words — short, dry, unbothered
- Total length: 220 to 240
- No emojis, hashtags, or narration

TONE:
- Humor = contrast (overreaction vs indifference)
- Educational value must feel effortless, not forced

AT THE END OF THE VIDEO THE SCIENTIST SAYS: "IF YOU WANT TO UNDERSTAND MORE CRAZY TECH NEWS, FOLLOW ME!" — this is non-negotiable. Make sure the script leads naturally to this line.:


Article:
{article_text}
"""

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _count_words(text: str) -> int:
    return len(text.split())


def _validate_script(script: str) -> bool:
    """Return True if *script* is a valid two-character dialogue."""
    wc = _count_words(script)
    if wc < config.SCRIPT_MIN_WORDS or wc > config.SCRIPT_MAX_WORDS:
        return False
    lines = [l.strip() for l in script.splitlines() if l.strip()]
    has_scientist = any(l.startswith("SCIENTIST:") for l in lines)
    has_villager  = any(l.startswith("VILLAGER:")  for l in lines)
    if not (has_scientist and has_villager):
        return False
    # All non-empty lines must be labelled
    if any(not (l.startswith("SCIENTIST:") or l.startswith("VILLAGER:")) for l in lines):
        return False
    return True


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str:
    """
    Call Ollama streaming API and assemble the full response text.
    Raises ScriptGenerationError on any HTTP/network error.
    """
    payload = {
        "model":  config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
    }
    try:
        response = requests.post(config.OLLAMA_URL, json=payload, timeout=120)
    except requests.exceptions.RequestException as exc:
        raise ScriptGenerationError(f"Network error calling Ollama: {exc}") from exc

    if response.status_code != 200:
        raise ScriptGenerationError(
            f"Ollama returned HTTP {response.status_code}"
        )

    parts = []
    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        parts.append(chunk.get("response", ""))
        if chunk.get("done"):
            break

    text = "".join(parts).strip()
    if not text:
        raise ScriptGenerationError("Ollama returned an empty response.")
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_VISUAL_QUERY_PROMPT = """\
You are selecting stock footage for a TikTok news video. For each SCIENTIST dialogue line below, write a concise 2-4 word Pexels image/video search query that would find visually relevant footage. Focus on concrete, photogenic subjects (people, objects, places, actions), not abstract concepts.

Lines:
{lines}

Reply with ONLY a JSON array of strings, one query per line, in order.
Example: ["Tesla electric car", "stock market graph", "factory workers assembly line"]
"""

_RANK_PROMPT_TEMPLATE = """\
You are a viral TikTok content editor. Given the following list of tech news headlines and summaries, choose the ONE article that would make the most engaging, funny, or surprising TikTok video for a general audience.

Criteria (in order of importance):
1. Surprising, absurd, or emotionally charged — something that makes people say "wait, what?"
2. Affects everyday people (not just niche developers or investors)
3. Has a clear, simple core idea that can be explained in 30 seconds
4. Controversy or irony is a bonus

Articles:
{articles_list}

Reply with ONLY the number of the best article (e.g. "3"). Nothing else.
"""


def pick_best_article(candidates: list[dict]) -> dict:
    """
    Use Ollama to rank *candidates* and return the most TikTok-worthy article dict.
    Falls back to the first candidate if ranking fails.
    """
    if len(candidates) == 1:
        return candidates[0]

    lines = []
    for i, art in enumerate(candidates, 1):
        summary = (art.get("summary") or "")[:200].replace("\n", " ")
        lines.append(f"{i}. [{art['source']}] {art['title']}\n   {summary}")

    prompt = _RANK_PROMPT_TEMPLATE.format(articles_list="\n\n".join(lines))

    try:
        raw = _call_ollama(prompt).strip()
        # Extract the first integer found in the response
        import re
        match = re.search(r"\d+", raw)
        if match:
            idx = int(match.group()) - 1
            if 0 <= idx < len(candidates):
                chosen = candidates[idx]
                logger.info(
                    "Ollama ranked article #%d as best: %s", idx + 1, chosen["title"]
                )
                return chosen
    except Exception as exc:
        logger.warning("Article ranking failed (%s) — falling back to first candidate.", exc)

    return candidates[0]


def generate_script(article: dict, backend: str = "ollama") -> str:
    """
    Generate a validated TikTok narration script for *article*.

    Parameters
    ----------
    article : dict
        Must contain at least: title, summary, full_text, url, source.
    backend : str
        Only "ollama" is supported for now; "openai" is a no-op placeholder
        that raises ValueError so callers know it is unsupported.

    Returns
    -------
    str
        The generated script, 60–150 words with a ≤15-word opening hook.

    Raises
    ------
    ScriptGenerationError
        If a valid script cannot be produced within SCRIPT_MAX_RETRIES attempts.
    ValueError
        If *backend* is not recognised, or *article* is missing required keys.
    """
    # --- input validation ---
    if backend not in ("ollama",):
        raise ValueError(f"Unsupported backend: {backend!r}. Only 'ollama' is supported.")

    for key in ("title", "summary", "full_text"):
        if key not in article:
            raise KeyError(f"Article dict is missing required key: {key!r}")

    article_text = (article["full_text"].strip() or article["summary"].strip())[:3000]
    if not article_text:
        raise ValueError("Article has neither full_text nor summary.")

    header = f"Headline: {article.get('title', '').strip()}\nSource: {article.get('source', '').strip()}\n\n"
    prompt = _PROMPT_TEMPLATE.format(article_text=header + article_text)
    logger.debug(
        "Prompt article snippet (first 300 chars): %s",
        (header + article_text)[:300],
    )

    # --- retry loop ---
    last_error: Optional[Exception] = None
    for attempt in range(1, config.SCRIPT_MAX_RETRIES + 1):
        try:
            raw = _call_ollama(prompt)
        except ScriptGenerationError as exc:
            last_error = exc
            logger.warning("Script attempt %d/%d failed: %s", attempt, config.SCRIPT_MAX_RETRIES, exc)
            continue

        if _validate_script(raw):
            logger.info("Script generated successfully on attempt %d.", attempt)
            return raw

        logger.warning(
            "Script attempt %d/%d failed validation (word count=%d).",
            attempt, config.SCRIPT_MAX_RETRIES, _count_words(raw),
        )

    raise ScriptGenerationError(
        f"Could not generate a valid script in {config.SCRIPT_MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def generate_visual_queries(script: str, timings: list) -> list[dict]:
    """
    Generate a contextual Pexels search query for each SCIENTIST timing segment.

    Parses the script lines in order (matching the order of *timings*) and asks
    Ollama to produce a 2-4 word visual search query for every SCIENTIST line.
    VILLAGER lines are omitted from the result (they're too short/reactive to
    yield useful footage queries).

    Parameters
    ----------
    script : str
        The full SCIENTIST/VILLAGER dialogue script.
    timings : list[dict]
        Timing segments from the TTS sidecar:
        ``[{"speaker": "SCIENTIST"|"VILLAGER", "start": float, "end": float}, ...]``
        Must be in the same order as the dialogue lines in *script*.

    Returns
    -------
    list[dict]
        ``[{"query": str, "start": float, "end": float}, ...]`` for each
        SCIENTIST segment that produced a usable query.  Returns ``[]`` on
        complete failure so callers can fall back gracefully.
    """
    # Parse script into (speaker, text) in dialogue order
    parsed_lines: list[tuple[str, str]] = []
    for ln in script.splitlines():
        ln = ln.strip()
        if ln.startswith("SCIENTIST:"):
            parsed_lines.append(("SCIENTIST", ln[len("SCIENTIST:"):].strip()))
        elif ln.startswith("VILLAGER:"):
            parsed_lines.append(("VILLAGER", ln[len("VILLAGER:"):].strip()))

    if len(parsed_lines) != len(timings):
        logger.warning(
            "Script has %d lines but timings has %d entries — aligning to shorter.",
            len(parsed_lines), len(timings),
        )
        min_len = min(len(parsed_lines), len(timings))
        parsed_lines = parsed_lines[:min_len]
        timings = timings[:min_len]

    scientist_entries = [
        (text, timings[i])
        for i, (spk, text) in enumerate(parsed_lines)
        if spk == "SCIENTIST"
    ]
    if not scientist_entries:
        return []

    # Single Ollama call with all SCIENTIST lines
    numbered = "\n".join(
        f"{j + 1}. {text}" for j, (text, _) in enumerate(scientist_entries)
    )
    prompt = _VISUAL_QUERY_PROMPT.format(lines=numbered)
    queries: list[str] = [""] * len(scientist_entries)
    try:
        raw = _call_ollama(prompt).strip()
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            for j, q in enumerate(parsed[: len(scientist_entries)]):
                queries[j] = str(q).strip()
    except Exception as exc:
        logger.warning("Visual query generation failed (%s) — using keyword fallback.", exc)

    result = []
    for j, (text, timing) in enumerate(scientist_entries):
        query = queries[j]
        if not query:
            # Fallback: last 3 content words from the SCIENTIST line
            words = [w for w in text.split() if len(w) > 3]
            query = " ".join(words[-3:]) if words else ""
        if query:
            result.append({
                "query": query,
                "start": timing["start"],
                "end":   timing["end"],
            })

    logger.info("Generated %d visual queries for SCIENTIST segments.", len(result))
    return result
