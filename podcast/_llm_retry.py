"""Shared Gemini transient-error retry helpers.

Used by LLM text-extraction (`content_parser/table/podcast.py`) and by
the audio subtitle generator (`subtitle_generator.py`). Kept in a small
module so both paths share identical backoff semantics.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Generator

try:
    from google.genai import errors as genai_errors
except ImportError:
    genai_errors = None  # type: ignore[misc, assignment]


def is_transient_llm_error(e: BaseException) -> bool:
    if genai_errors is not None and isinstance(e, genai_errors.APIError):
        return e.code in (408, 429, 500, 502, 503, 504)
    et = type(e).__name__
    if et in ("ReadTimeout", "ConnectTimeout", "RemoteProtocolError", "ConnectError"):
        return True
    s = str(e).lower()
    return any(
        x in s
        for x in (
            "503",
            "429",
            "502",
            "504",
            "unavailable",
            "resource exhausted",
            "try again later",
            "high demand",
            "overloaded",
            "deadline exceeded",
        )
    )


def gemini_retry_params() -> tuple[int, float]:
    max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "6"))
    base = float(os.getenv("GEMINI_RETRY_BASE_SEC", "2"))
    return max(1, max_retries), max(0.5, base)


def invoke_with_transient_retry(fn: Callable[[], Any]) -> Any:
    max_retries, base = gemini_retry_params()
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if not is_transient_llm_error(e):
                raise
            if attempt >= max_retries - 1:
                raise
            delay = min(base * (2**attempt), 120.0)
            logging.warning(
                "Gemini 暂不可用: %s；%.1f 秒后重试 (%s/%s)",
                e,
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)


def stream_with_transient_retry(
    stream_factory: Callable[[], Generator[Any, None, None]],
) -> Generator[Any, None, None]:
    max_retries, base = gemini_retry_params()
    attempt = 0
    while attempt < max_retries:
        try:
            yield from stream_factory()
            return
        except Exception as e:
            if not is_transient_llm_error(e):
                raise
            attempt += 1
            if attempt >= max_retries:
                raise
            delay = min(base * (2 ** (attempt - 1)), 120.0)
            logging.warning(
                "Gemini 暂不可用: %s；%.1f 秒后重试 (%s/%s)",
                e,
                delay,
                attempt,
                max_retries,
            )
            time.sleep(delay)
