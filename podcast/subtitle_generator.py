"""Word-level podcast subtitle generator using Gemini audio understanding.

Takes a podcast mp3 and asks Gemini to emit structured per-segment / per-token
timing, then writes out four subtitle artifacts suitable for karaoke-style
word highlighting in a web player or video caption track:

- `<stem>.words.json`  JSON with segments[{speaker,text,start,end,words[...]}]
- `<stem>.words.vtt`   WebVTT with inline `<00:00:00.500>` time tags per token
- `<stem>.words.lrc`   Enhanced LRC (A2 extension) per token
- `<stem>.srt`         Classic SRT (sentence-level)

CLI:
    subtitle-gen generate audios/podcast/foo.mp3 --language zh
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Iterable, List, Optional

import typer
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from .content_parser import types as lang_types
from ._llm_retry import invoke_with_transient_retry
from .gemini_config import (
    gemini_api_key,
    gemini_http_options,
    subtitle_uses_inline_audio,
)

load_dotenv(override=True)

app = typer.Typer()


@app.callback()
def _main() -> None:
    """Gemini audio → word-level subtitles (json / vtt / lrc / srt)."""


SUPPORTED_FORMATS = ("json", "vtt", "lrc", "srt")
_UPLOAD_POLL_INTERVAL = 1.5
_UPLOAD_POLL_TIMEOUT = 120.0
_MAX_OUTPUT_TOKENS = 65535
_DEFAULT_CHUNK_SEC = 180  # 3 分钟：CJK 短语切片在 65k output tokens 内安全
_MIN_CHUNK_SEC = 30       # MAX_TOKENS 时自适应分段的下界


class MaxTokensError(RuntimeError):
    """Gemini 输出被 MAX_TOKENS 截断；上层应将该分片再切半重试。"""


# ---------- Pydantic timing models --------------------------------------- #


class WordTiming(BaseModel):
    text: str = Field(..., description="Token text. A single word for space-separated languages; a short 2-5 character phrase for CJK.")
    start: float = Field(..., description="Token start time in seconds.")
    end: float = Field(..., description="Token end time in seconds.")


class SegmentTiming(BaseModel):
    speaker: str = Field(
        default="",
        description="Role / speaker label if identifiable from the audio. Empty string if unknown.",
    )
    text: str = Field(..., description="Full text of this speech segment.")
    start: float = Field(..., description="Segment start in seconds.")
    end: float = Field(..., description="Segment end in seconds.")
    words: List[WordTiming] = Field(default_factory=list)


class WordLevelSubtitles(BaseModel):
    language: str
    duration: float = Field(..., description="Total audio duration in seconds.")
    segments: List[SegmentTiming]


# ---------- Gemini audio transcription ----------------------------------- #


def _subtitle_model() -> str:
    return os.getenv("GEMINI_SUBTITLE_MODEL", "gemini-2.5-flash")


def _chunk_sec() -> int:
    try:
        return max(30, int(os.getenv("SUBTITLE_CHUNK_SEC", str(_DEFAULT_CHUNK_SEC))))
    except ValueError:
        return _DEFAULT_CHUNK_SEC


def _mime_for(path: str) -> str:
    ext = Path(path).suffix.lower().lstrip(".")
    return {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
    }.get(ext, "audio/mpeg")


def _build_prompt(language: str, script_hint: Optional[str]) -> str:
    lang_name = lang_types.TO_LLM_LANGUAGE.get(language, language)
    lang_key = language.split("-")[0].lower()
    is_cjk = lang_key in ("zh", "ja", "ko")

    tokenization = (
        "Split the text into natural short phrases of 2–5 characters (never single characters). "
        "Each phrase is one `words[i]` token with its own start/end."
        if is_cjk
        else "Every single word is one `words[i]` token. Punctuation attaches to the word before it."
    )

    speaker_hint = (
        "If you can identify distinct speakers by voice timbre, label them "
        '"Role1", "Role2", ... consistently across segments; otherwise leave `speaker` as "".'
    )

    hint_block = (
        f"\nREFERENCE TRANSCRIPT (for alignment only — do NOT invent text that is not spoken):\n"
        f"<transcript>\n{script_hint.strip()}\n</transcript>\n"
        if script_hint and script_hint.strip()
        else ""
    )

    return f"""You are an expert audio-subtitle aligner.

Transcribe the provided podcast audio in {lang_name} and return structured timing in JSON.

Rules:
- All timestamps are seconds as float with at least 2 decimals of precision. Start at 0.0.
- Break the transcript into `segments`, each one a continuous utterance by a single speaker.
- Each segment's `text` is the concatenation of its tokens (no added punctuation beyond what is spoken).
- {tokenization}
- {speaker_hint}
- Every `words[i].end` MUST be >= `words[i].start` and ordered monotonically.
- `segments[i].start` = first word's start; `segments[i].end` = last word's end.
- `duration` = end time of the last word (i.e. the total audio length).
- Preserve the original language; do not translate.
- Do not add commentary or explanations — return JSON only, matching the provided schema.
{hint_block}"""


def _upload_and_wait(client, audio_path: str):
    """Upload the file and poll until it is ACTIVE. Returns the File object."""
    from google.genai import types as genai_types

    uploaded = client.files.upload(
        file=audio_path,
        config=genai_types.UploadFileConfig(mime_type=_mime_for(audio_path)),
    )
    deadline = time.time() + _UPLOAD_POLL_TIMEOUT
    while getattr(uploaded, "state", None) and str(uploaded.state).upper().endswith("PROCESSING"):
        if time.time() > deadline:
            raise TimeoutError(f"Gemini file {uploaded.name} stuck in PROCESSING")
        time.sleep(_UPLOAD_POLL_INTERVAL)
        uploaded = client.files.get(name=uploaded.name)
    state = str(getattr(uploaded, "state", "")).upper()
    if state and not state.endswith("ACTIVE"):
        raise RuntimeError(f"Gemini file upload failed: state={state}, error={uploaded.error}")
    return uploaded


def generate_word_level_subtitles(
    audio_path: str,
    language: str = "en",
    script_hint: Optional[str] = None,
    model: Optional[str] = None,
    chunk_sec: Optional[int] = None,
) -> WordLevelSubtitles:
    """Send `audio_path` to Gemini and return word-level timing data.

    For audio longer than `chunk_sec` (default 3 min, `SUBTITLE_CHUNK_SEC` env),
    the audio is split into sequential chunks and each is transcribed separately;
    returned segments/words are re-offset by each chunk's start time.

    If a chunk's response hits `MAX_TOKENS`, the chunk is recursively halved
    (down to `_MIN_CHUNK_SEC`) and re-transcribed, so a single dense CJK segment
    never kills the whole run.
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(audio_path)

    from google import genai

    api_key = gemini_api_key()
    http_opt = gemini_http_options()
    client = (
        genai.Client(api_key=api_key, http_options=http_opt)
        if http_opt is not None
        else genai.Client(api_key=api_key)
    )

    model_id = model or _subtitle_model()
    csec = chunk_sec if chunk_sec is not None else _chunk_sec()

    chunks, tmp_dir = _chunk_audio(audio_path, csec)
    inline_audio = subtitle_uses_inline_audio()
    if inline_audio:
        logging.info(
            "subtitle: using inline audio (Files API upload skipped); "
            "set GEMINI_SUBTITLE_INLINE_AUDIO=0 to force resumable upload"
        )
    try:
        all_segments: list[SegmentTiming] = []
        total_duration = 0.0
        for idx, (chunk_path, offset_sec, chunk_dur) in enumerate(chunks):
            logging.info(
                "subtitle chunk %d/%d: %s (offset=%.1fs, dur=%.1fs)",
                idx + 1, len(chunks), os.path.basename(chunk_path), offset_sec, chunk_dur,
            )
            segments, ended_at = _transcribe_with_adaptive_split(
                client, chunk_path, language, script_hint, model_id,
                base_offset=offset_sec, max_sub_sec=max(csec, _MIN_CHUNK_SEC),
                inline_audio=inline_audio,
            )
            all_segments.extend(segments)
            total_duration = max(total_duration, ended_at or (offset_sec + chunk_dur))
    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    subs = WordLevelSubtitles(
        language=(all_segments and language) or language,
        duration=total_duration,
        segments=all_segments,
    )
    _sanitize(subs)
    return subs


def _transcribe_with_adaptive_split(
    client,
    chunk_path: str,
    language: str,
    script_hint: Optional[str],
    model_id: str,
    *,
    base_offset: float,
    max_sub_sec: int,
    inline_audio: bool,
) -> tuple[list[SegmentTiming], float]:
    """Transcribe a single chunk; if MAX_TOKENS, split in half and recurse.

    Returns (offset-adjusted segments, end_time_in_full_audio).
    """
    from pydub import AudioSegment

    try:
        part = _transcribe_once(
            client, chunk_path, language, script_hint, model_id, inline_audio=inline_audio
        )
    except MaxTokensError as e:
        audio = AudioSegment.from_file(chunk_path)
        dur_sec = len(audio) / 1000.0
        next_sub = max(_MIN_CHUNK_SEC, int(dur_sec // 2))
        if next_sub >= max_sub_sec or dur_sec <= _MIN_CHUNK_SEC:
            # Already at / below the floor — no point splitting further.
            logging.error(
                "MAX_TOKENS at minimum chunk size (dur=%.1fs); dropping this slice: %s",
                dur_sec, e,
            )
            return [], base_offset + dur_sec
        logging.warning(
            "MAX_TOKENS at %.1fs chunk; splitting into %ss pieces and retrying",
            dur_sec, next_sub,
        )
        subchunks, sub_tmp_dir = _chunk_audio(chunk_path, next_sub)
        try:
            out_segments: list[SegmentTiming] = []
            end_time = base_offset
            for sub_path, sub_off, sub_dur in subchunks:
                segs, sub_end = _transcribe_with_adaptive_split(
                    client, sub_path, language, script_hint, model_id,
                    base_offset=base_offset + sub_off,
                    max_sub_sec=next_sub,
                    inline_audio=inline_audio,
                )
                out_segments.extend(segs)
                end_time = max(end_time, sub_end)
            return out_segments, end_time
        finally:
            if sub_tmp_dir and os.path.isdir(sub_tmp_dir):
                shutil.rmtree(sub_tmp_dir, ignore_errors=True)

    # Success path: offset segments into full-audio timeline.
    out: list[SegmentTiming] = []
    end_time = base_offset
    for seg in part.segments:
        seg.start += base_offset
        seg.end += base_offset
        for w in seg.words:
            w.start += base_offset
            w.end += base_offset
        out.append(seg)
        end_time = max(end_time, seg.end)
    # Trust part.duration for a more accurate ending if it came through.
    if part.duration:
        end_time = max(end_time, base_offset + part.duration)
    return out, end_time


def _chunk_audio(audio_path: str, chunk_sec: int) -> tuple[list[tuple[str, float, float]], Optional[str]]:
    """Split audio into chunks. Returns ([(path, offset_sec, duration_sec)...], tmp_dir_or_None).

    For audio <= chunk_sec, returns the original path (no tmp dir).
    """
    from pydub import AudioSegment

    audio = AudioSegment.from_file(audio_path)
    total_ms = len(audio)
    step_ms = max(30_000, chunk_sec * 1000)
    if total_ms <= step_ms:
        return [(audio_path, 0.0, total_ms / 1000.0)], None

    tmp_dir = tempfile.mkdtemp(prefix="subs_chunks_")
    stem = Path(audio_path).stem
    ext = Path(audio_path).suffix.lstrip(".") or "mp3"
    out: list[tuple[str, float, float]] = []
    idx = 0
    for start_ms in range(0, total_ms, step_ms):
        end_ms = min(start_ms + step_ms, total_ms)
        seg = audio[start_ms:end_ms]
        path = os.path.join(tmp_dir, f"{stem}_chunk_{idx:03d}.{ext}")
        seg.export(path, format=ext if ext in ("mp3", "wav", "ogg", "flac") else "mp3")
        out.append((path, start_ms / 1000.0, (end_ms - start_ms) / 1000.0))
        idx += 1
    return out, tmp_dir


def _transcribe_once(
    client,
    audio_path: str,
    language: str,
    script_hint: Optional[str],
    model_id: str,
    *,
    inline_audio: bool,
) -> WordLevelSubtitles:
    """Send one audio file to Gemini and return structured timing (single call)."""
    from google.genai import types as genai_types

    prompt = _build_prompt(language, script_hint)
    mime = _mime_for(audio_path)

    if inline_audio:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        audio_part = genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime)
        contents: list = [audio_part, prompt]

        def _call():
            return client.models.generate_content(
                model=model_id,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=WordLevelSubtitles,
                    temperature=0.1,
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                ),
            )

        response = invoke_with_transient_retry(_call)
    else:
        uploaded = invoke_with_transient_retry(lambda: _upload_and_wait(client, audio_path))
        try:
            def _call():
                return client.models.generate_content(
                    model=model_id,
                    contents=[uploaded, prompt],
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=WordLevelSubtitles,
                        temperature=0.1,
                        max_output_tokens=_MAX_OUTPUT_TOKENS,
                    ),
                )

            response = invoke_with_transient_retry(_call)
        finally:
            try:
                client.files.delete(name=uploaded.name)
            except Exception as e:  # noqa: BLE001
                logging.warning("Failed to delete Gemini file %s: %s", uploaded.name, e)

    finish_reason = _finish_reason(response)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, WordLevelSubtitles):
        return parsed

    # Fallback: raw JSON. If truncated by MAX_TOKENS we'll get broken JSON.
    raw = getattr(response, "text", "") or ""
    if finish_reason and "MAX_TOKENS" in finish_reason:
        raise MaxTokensError(
            f"Gemini output truncated by MAX_TOKENS (chunk too long). text[:200]={raw[:200]!r}"
        )
    try:
        payload = json.loads(raw)
    except Exception as e:
        raise RuntimeError(
            f"Gemini returned non-JSON subtitle payload: {e}; finish_reason={finish_reason}; text[:300]={raw[:300]!r}"
        )
    try:
        return WordLevelSubtitles.model_validate(payload)
    except ValidationError as e:
        raise RuntimeError(f"Gemini subtitle payload failed schema validation: {e}")


def _finish_reason(response) -> str:
    try:
        cands = getattr(response, "candidates", None) or []
        if cands:
            fr = getattr(cands[0], "finish_reason", None)
            return str(fr) if fr is not None else ""
    except Exception:  # noqa: BLE001
        pass
    return ""


def _sanitize(subs: WordLevelSubtitles) -> None:
    """Monotonic non-negative times; fix trivial overlaps from the model."""
    last = 0.0
    for seg in subs.segments:
        prev_word_end = max(seg.start, last)
        for w in seg.words:
            if w.start < prev_word_end:
                w.start = prev_word_end
            if w.end < w.start:
                w.end = w.start
            prev_word_end = w.end
        if seg.words:
            seg.start = min(seg.start, seg.words[0].start)
            seg.end = max(seg.end, seg.words[-1].end)
        last = max(last, seg.end)
    if subs.segments:
        subs.duration = max(subs.duration, subs.segments[-1].end)


# ---------- Timestamp formatting ----------------------------------------- #


def _fmt_vtt(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _fmt_srt(t: float) -> str:
    return _fmt_vtt(t).replace(".", ",")


def _fmt_lrc(t: float) -> str:
    t = max(0.0, float(t))
    m = int(t // 60)
    s = t - m * 60
    return f"{m:02d}:{s:05.2f}"


# ---------- Writers ------------------------------------------------------- #


def write_json(subs: WordLevelSubtitles, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(subs.model_dump_json(indent=2))
    return path


def write_vtt(subs: WordLevelSubtitles, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["WEBVTT", ""]
    for idx, seg in enumerate(subs.segments, 1):
        lines.append(str(idx))
        lines.append(f"{_fmt_vtt(seg.start)} --> {_fmt_vtt(seg.end)}")
        if seg.speaker:
            prefix = f"<v {seg.speaker}>"
        else:
            prefix = ""
        body = _inline_tagged(seg, joiner_for(subs.language))
        lines.append(prefix + body)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return path


def write_lrc(subs: WordLevelSubtitles, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "[ti:Podcast]",
        f"[length:{_fmt_lrc(subs.duration)}]",
    ]
    joiner = joiner_for(subs.language)
    for seg in subs.segments:
        tagged = []
        for w in seg.words:
            tagged.append(f"<{_fmt_lrc(w.start)}>{w.text}")
        body = joiner.join(tagged) if tagged else seg.text
        prefix = f"{seg.speaker}: " if seg.speaker else ""
        lines.append(f"[{_fmt_lrc(seg.start)}]{prefix}{body}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def write_srt(subs: WordLevelSubtitles, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for idx, seg in enumerate(subs.segments, 1):
        lines.append(str(idx))
        lines.append(f"{_fmt_srt(seg.start)} --> {_fmt_srt(seg.end)}")
        prefix = f"{seg.speaker}: " if seg.speaker else ""
        lines.append(prefix + (seg.text or joiner_for(subs.language).join(w.text for w in seg.words)))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return path


def joiner_for(language: str) -> str:
    """No space between tokens for CJK, single space otherwise."""
    return "" if language.split("-")[0].lower() in ("zh", "ja", "ko") else " "


def _inline_tagged(seg: SegmentTiming, joiner: str) -> str:
    if not seg.words:
        return seg.text or ""
    parts = [f"<{_fmt_vtt(w.start)}>{w.text}" for w in seg.words]
    return joiner.join(parts)


WRITERS = {
    "json": (".words.json", write_json),
    "vtt": (".words.vtt", write_vtt),
    "lrc": (".words.lrc", write_lrc),
    "srt": (".srt", write_srt),
}


def write_all(
    subs: WordLevelSubtitles,
    audio_path: str,
    output_dir: Optional[str] = None,
    formats: Iterable[str] = SUPPORTED_FORMATS,
) -> dict[str, str]:
    """Write selected formats alongside `audio_path` (or in `output_dir`). Returns {fmt: path}."""
    base_dir = output_dir or str(Path(audio_path).parent)
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    stem = Path(audio_path).stem
    out: dict[str, str] = {}
    for fmt in formats:
        if fmt not in WRITERS:
            logging.warning("Unknown subtitle format %r, skipping", fmt)
            continue
        suffix, writer = WRITERS[fmt]
        path = str(Path(base_dir) / f"{stem}{suffix}")
        writer(subs, path)
        out[fmt] = path
    return out


# ---------- CLI ---------------------------------------------------------- #


@app.command("generate")
def cli_generate(
    audio_file: str,
    language: str = "en",
    script_file: str = typer.Option("", help="Optional text transcript to help Gemini align tokens."),
    output_dir: str = typer.Option("", help="Directory for generated subtitle files; defaults to audio_file's dir."),
    formats: List[str] = typer.Option(list(SUPPORTED_FORMATS), help="Formats to emit: json, vtt, lrc, srt."),
    model: str = typer.Option("", help="Override GEMINI_SUBTITLE_MODEL."),
    chunk_sec: int = typer.Option(
        0,
        help="Split audio into chunks of this many seconds before sending to Gemini. 0 = use SUBTITLE_CHUNK_SEC env or default 300.",
    ),
):
    """Transcribe AUDIO_FILE via Gemini and write word-level subtitle files."""
    script_hint: Optional[str] = None
    if script_file:
        with open(script_file, "r", encoding="utf-8") as f:
            script_hint = f.read()

    subs = generate_word_level_subtitles(
        audio_file,
        language=language,
        script_hint=script_hint,
        model=model or None,
        chunk_sec=chunk_sec if chunk_sec > 0 else None,
    )
    out = write_all(
        subs,
        audio_path=audio_file,
        output_dir=output_dir or None,
        formats=formats,
    )
    for fmt, path in out.items():
        typer.echo(f"{fmt}: {path}")
    typer.echo(f"segments={len(subs.segments)} duration={subs.duration:.2f}s language={subs.language}")


r"""
python -m podcast.subtitle_generator generate \
    audios/podcast/LLM.mp3 \
    --language zh
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    app()
