"""
Pipeline package.

Imports are done lazily here so that optional heavy dependencies
(TTS, faster-whisper, ffmpeg-python, newspaper3k, trafilatura) do NOT need
to be installed just to run tests – each module guards its own heavy imports.
"""


def fetch_latest_news(*args, **kwargs):
    from pipeline.news_fetcher import fetch_latest_news as _f
    return _f(*args, **kwargs)


def fetch_candidate_articles(*args, **kwargs):
    from pipeline.news_fetcher import fetch_candidate_articles as _f
    return _f(*args, **kwargs)


def hydrate_article(*args, **kwargs):
    from pipeline.news_fetcher import hydrate_article as _f
    return _f(*args, **kwargs)


def log_video_made(*args, **kwargs):
    from pipeline.news_fetcher import log_video_made as _f
    return _f(*args, **kwargs)


def pick_best_article(*args, **kwargs):
    from pipeline.script_writer import pick_best_article as _f
    return _f(*args, **kwargs)


def generate_script(*args, **kwargs):
    from pipeline.script_writer import generate_script as _f
    return _f(*args, **kwargs)


def generate_voiceover(*args, **kwargs):
    from pipeline.tts_engine import generate_voiceover as _f
    return _f(*args, **kwargs)


def extract_word_timestamps(*args, **kwargs):
    from pipeline.caption_sync import extract_word_timestamps as _f
    return _f(*args, **kwargs)


def group_into_caption_chunks(*args, **kwargs):
    from pipeline.caption_sync import group_into_caption_chunks as _f
    return _f(*args, **kwargs)


def compose_video(*args, **kwargs):
    from pipeline.video_composer import compose_video as _f
    return _f(*args, **kwargs)


def get_background_video(*args, **kwargs):
    from pipeline.background_source import get_background_video as _f
    return _f(*args, **kwargs)


def fetch_media_inserts(*args, **kwargs):
    from pipeline.media_fetcher import fetch_media_inserts as _f
    return _f(*args, **kwargs)


def generate_visual_queries(*args, **kwargs):
    from pipeline.script_writer import generate_visual_queries as _f
    return _f(*args, **kwargs)


__all__ = [
    "fetch_latest_news",
    "fetch_candidate_articles",
    "hydrate_article",
    "log_video_made",
    "pick_best_article",
    "generate_script",
    "generate_voiceover",
    "extract_word_timestamps",
    "group_into_caption_chunks",
    "compose_video",
    "get_background_video",
    "fetch_media_inserts",
    "generate_visual_queries",
]
