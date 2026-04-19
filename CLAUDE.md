# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`gen-podcast` is an AI-powered podcast generation tool. It extracts content from web pages, YouTube videos, and PDFs → generates multi-role dialogue scripts via Google Gemini → synthesizes speech with Edge TTS → stores audio/metadata in Cloudflare R2 (object storage) and D1 (SQLite database).

## Commands

This project uses `uv` as the package manager and `typer` for CLI apps.

```bash
# Install in editable mode
make install           # or: pip install -e .

# Build distribution
make build

# Run main CLI
make gen-podcast ARGS="https://example.com"
gen-podcast run "https://example.com"

# Generate RSS feed from D1
make gen-rss
gen-podcasts-xml gen-podcasts-feed-xml

# Generate RSS and upload to R2
make gen-rss-upload
```

There are no test or lint commands defined in this project.

## CLI Entry Points

Defined in `pyproject.toml` under `[project.scripts]`:

| Command              | Module                                                    | Purpose                                         |
| -------------------- | --------------------------------------------------------- | ----------------------------------------------- |
| `gen-podcast`        | `podcast.gen_podcast:app`                                 | End-to-end orchestrator                         |
| `gen-podcasts-xml`   | `podcast.gen_podcasts_xml:app`                            | RSS feed generation                             |
| `content-parser-tts` | `podcast.content_parser_tts:app`                          | Content extraction + TTS only                   |
| `insert-podcast`     | `podcast.insert_podcast:app`                              | R2 upload + D1 insert                           |
| `siliconflow-api`    | `podcast.siliconflow_api:app`                             | AI cover image generation                       |
| `content-extractor`  | `podcast.content_parser.content_extractor_instructor:app` | Content extraction only                         |
| `subtitle-gen`       | `podcast.subtitle_generator:app`                          | Word-level subtitle generation via Gemini audio |

## Architecture

### Pipeline Flow

```
gen-podcast run <SOURCE>
  → ContentExtractor (router: YouTube / Website / PDF)
  → Gemini LLM via instructor → Podcast(title, description, roles[])
  → Edge TTS per role → MP3 + VTT files
  → pydub merge → final audio
  → SiliconFlow AI → cover image
  → Gemini audio → word-level subtitles (json/vtt/lrc/srt)  [opt-in via --subtitles]
  → Cloudflare R2 upload (audio + cover + subtitles)
  → Cloudflare D1 insert
```

### Key Modules

**`podcast/gen_podcast.py`** — Main orchestrator. Calls `instruct_content_tts()`, then `_gen_and_upload_subtitles()`, then `insert_podcast_to_d1()`.

**`podcast/content_parser/`** — Content extraction pipeline:

- `content_extractor_instructor.py` — Routes to appropriate extractor based on source type
- `youtube_transcriber_instructor.py` — Fetches YouTube captions via `youtube-transcript-api`
- `website_extractor_instructor.py` — HTML extraction via BeautifulSoup
- `pdf_extractor_instructor.py` — PDF text via PyMuPDF; handles arXiv URLs specially
- `table/podcast.py` — Pydantic models (`Role`, `Podcast`) + Gemini LLM integration via `instructor`

**`podcast/content_parser_tts.py`** — Async Edge TTS synthesis with 4-level fallback strategy (rate/boundary variations), then segment-and-merge if all fail. Outputs `.mp3` + `.vtt`.

**`podcast/subtitle_generator.py`** — Uploads the final merged MP3 to Gemini, requests JSON-schema-bound word-level timing (segments/words start/end seconds), writes 4 artifacts alongside the mp3: `.words.json` (front-end render), `.words.vtt` (WebVTT with inline `<00:00:00.500>` karaoke tags), `.words.lrc` (A2-extension per-word LRC), `.srt` (sentence-level). CJK languages get 2–5-char phrase tokens; space-separated languages get per-word tokens.

**`podcast/_llm_retry.py`** — Shared Gemini transient-error retry helpers (`invoke_with_transient_retry`, `stream_with_transient_retry`). Used by both text LLM and audio subtitle paths.

**`podcast/cloudflare/rest_api.py`** — Cloudflare D1 REST API wrapper.

**`podcast/aws/upload.py`** — Cloudflare R2 upload via `boto3` (S3-compatible).

**`podcast/gen_podcasts_xml.py`** — Generates Apple Podcasts-compatible RSS XML from D1 data.

### LLM Integration

Uses `google-genai` SDK with `instructor` for structured outputs. The primary model is `GEMINI_MODEL` (default `gemini-3-flash-preview`) with an optional `GEMINI_FALLBACK_MODEL` on 503 errors. Retries use exponential backoff (`GEMINI_RETRY_BASE_SEC`, default 2s, up to `GEMINI_MAX_RETRIES`, default 6).

Streaming is preferred: `create_partial()` for single objects, `create_iterable()` for lists.

### D1 Database Schema

The `podcast` table tracks: `pid` (unique ID), `title`, `author`, `speakers`, `source` (youtube/pdf/text), `audio_url`, `cover_img_url`, `description`, `audio_content`, `duration` (seconds), `category` (0–8), `status` (0–5), `is_published`, timestamps, `audio_size`, plus 4 subtitle URL columns: `subtitle_json_url`, `subtitle_vtt_url`, `subtitle_lrc_url`, `subtitle_srt_url`. Existing deployments need `ALTER TABLE podcast ADD COLUMN subtitle_*_url text DEFAULT "";` — see the migration block at the top of `podcast/insert_podcast.py`.

## Environment Variables

Copy `.env.example` to `.env`. Required keys:

```bash
GOOGLE_API_KEY=              # Gemini API
GEMINI_MODEL=                # e.g. gemini-3-flash-preview
GEMINI_SUBTITLE_MODEL=       # optional; audio-capable model, default gemini-2.5-flash
PODCAST_D1_DB_ID=            # Cloudflare D1 database ID
CLOUDFLARE_API_KEY=          # Cloudflare API key
CLOUDFLARE_ACCOUNT_ID=       # Cloudflare account
CLOUDFLARE_ACCESS_KEY=       # R2 access key
CLOUDFLARE_SECRET_KEY=       # R2 secret key
S3_BUCKET_URL=               # Public URL prefix for R2 bucket
SILICONCLOUD_API_KEY=        # SiliconFlow image generation
```

---

MUST: **please answer in the same language as the user's request.**
