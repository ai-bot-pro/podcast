"""Gemini Developer API 环境变量（与 .env / .env.example 中 GEMINI_*、GOOGLE_API_KEY 对齐）。"""

from __future__ import annotations

import os
from typing import Optional

from google.genai import types as genai_types


def gemini_api_key() -> str:
    """优先 GOOGLE_API_KEY，其次 GEMINI_API_KEY。"""
    key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GOOGLE_API_KEY / GEMINI_API_KEY 未设置（请在 .env 中配置）")
    return key


def subtitle_uses_inline_audio() -> bool:
    """字幕是否内联字节发送音频（不经 Files API 分块上传）。

    自定义 GEMINI_BASE_URL 的网关常不转发 x-goog-upload-url，files.upload 会失败。
    显式 GEMINI_SUBTITLE_INLINE_AUDIO=true/false 可覆盖自动行为。
    """
    override = (os.getenv("GEMINI_SUBTITLE_INLINE_AUDIO") or "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False
    return bool((os.getenv("GEMINI_BASE_URL") or "").strip())


def gemini_http_options() -> Optional[genai_types.HttpOptions]:
    """根据 GEMINI_BASE_URL、GEMINI_PROXY_URL 构造 google-genai 的 HttpOptions（可不设）。"""
    base_url = (os.getenv("GEMINI_BASE_URL") or "").strip()
    proxy_url = (os.getenv("GEMINI_PROXY_URL") or "").strip()
    if not base_url and not proxy_url:
        return None
    opts: dict = {}
    if base_url:
        opts["base_url"] = base_url
    if proxy_url:
        opts["client_args"] = {"proxy": proxy_url}
        opts["async_client_args"] = {"proxy": proxy_url}
    return genai_types.HttpOptions(**opts)
