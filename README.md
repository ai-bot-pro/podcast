![aipodcast](https://github.com/user-attachments/assets/b78dd807-9e27-4f66-84c0-2a78b9b14388)

# AI Bot Pro — Podcast

<p align="center">
  <a href="https://pypi.org/project/gen-podcast/"><img src="https://img.shields.io/pypi/v/gen-podcast?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/gen-podcast/"><img src="https://img.shields.io/pypi/pyversions/gen-podcast?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/ai-bot-pro/podcast/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://weedge.github.io/about/"><img src="https://img.shields.io/badge/Built%20by-weedge-blueviolet?style=for-the-badge" alt="Built by weedge"></a>
</p>

[English](./README.md) | [中文](./README_CN.md)

An AI-powered podcast generation tool: automatically extract text from any source (webpage, YouTube, PDF) → generate multi-role dialogue scripts via Gemini LLM → synthesize speech with Edge TTS → store in Cloudflare R2 + Cloudflare D1.

- AI Podcast: https://podcast-997.pages.dev/
- AI Podcast UI & Cloudflare Worker: https://github.com/ai-bot-pro/react-nextjs-web-podcast

---

## Features

| Step                   | Description                                                                                           |
| ---------------------- | ----------------------------------------------------------------------------------------------------- |
| **Content Extraction** | Supports webpages (BeautifulSoup), YouTube (subtitles/transcription), PDF (PyMuPDF)                   |
| **Script Generation**  | Gemini (`google-genai` + `instructor`) streams multi-role podcast dialogue                            |
| **Speech Synthesis**   | Microsoft Edge TTS, supports Chinese/English/Japanese/Korean and more, with exponential backoff retry |
| **Cover Art**          | SiliconFlow AI image generation, auto-compressed and uploaded to Cloudflare R2                        |
| **Storage / Database** | Cloudflare R2 (audio/images) + Cloudflare D1 (metadata)                                               |
| **RSS Feed**           | Generate Apple Podcasts-compatible RSS XML from D1, optionally upload to R2                            |

---

## Project Structure

```
podcast/
├── pyproject.toml
├── .env.example
├── podcast/
│   ├── gen_podcast.py              # End-to-end CLI entry point
│   ├── gen_podcasts_xml.py         # Generate RSS feed XML from D1
│   ├── content_parser_tts.py       # Content extraction + TTS
│   ├── insert_podcast.py           # R2 upload + D1 insert
│   ├── audio_length.py
│   ├── image_compression.py
│   ├── siliconflow_api.py
│   ├── aws/
│   │   └── upload.py               # Cloudflare R2 via boto3
│   ├── cloudflare/
│   │   └── rest_api.py             # D1 REST API
│   └── content_parser/
│       ├── types.py                # Language code mapping
│       ├── content_extractor_instructor.py
│       ├── pdf_extractor_instructor.py
│       ├── website_extractor_instructor.py
│       ├── youtube_transcriber_instructor.py
│       └── table/
│           └── podcast.py          # LLM prompt + structured output
└── audios/                         # Generated audio files (gitignored)
```

---

## Installation

```bash
# Python 3.11+ recommended
pip install gen-podcast

# Or install from source in editable mode
cd podcast
make install   # equivalent to: pip install -e .
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable                | Description                                                           |
| ----------------------- | --------------------------------------------------------------------- |
| `GOOGLE_API_KEY`        | Google Gemini API key                                                 |
| `GEMINI_MODEL`          | Model ID, default `gemini-3-flash-preview` (without `models/` prefix) |
| `GEMINI_FALLBACK_MODEL` | Optional fallback model on 503 overload (e.g. `gemini-2.5-flash`)     |
| `GEMINI_MAX_RETRIES`    | LLM retry count, default `6`                                          |
| `GEMINI_RETRY_BASE_SEC` | Retry base delay in seconds (exponential backoff), default `2`        |
| `ROUND_CN`              | Number of dialogue rounds (optional, random 20–50 if unset)           |
| `PODCAST_D1_DB_ID`      | Cloudflare D1 database ID                                             |
| `CLOUDFLARE_API_KEY`    | Cloudflare API Token                                                  |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID                                                 |
| `CLOUDFLARE_ACCESS_KEY` | R2 Access Key                                                         |
| `CLOUDFLARE_SECRET_KEY` | R2 Secret Key                                                         |
| `CLOUDFLARE_REGION`     | R2 region, default `apac`                                             |
| `S3_BUCKET_URL`         | R2 public base URL                                                    |
| `SILICONCLOUD_API_KEY`  | SiliconFlow API key (for cover art generation)                        |

---

## Quick Start

### End-to-End Generation (Recommended)

```bash
# English podcast
gen-podcast run \
    "https://en.wikipedia.org/wiki/Large_language_model"

# Chinese podcast (specify Chinese voices)
gen-podcast run \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    --category 1 \
    "https://en.wikipedia.org/wiki/Large_language_model"

# Multiple sources + publish
gen-podcast run \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    --category 1 \
    --is-published \
    "https://www.youtube.com/watch?v=aR6CzM0x-g0" \
    "https://en.wikipedia.org/wiki/Large_language_model" \
    "/path/to/paper.pdf"

# Or use make (pass extra arguments via ARGS)
make gen-podcast ARGS="--language zh https://en.wikipedia.org/wiki/Large_language_model"
```

`run` options:

| Option              | Default                                | Description                                                      |
| ------------------- | -------------------------------------- | ---------------------------------------------------------------- |
| `SOURCES`           | —                                      | One or more sources (webpage URL / YouTube URL / PDF path)       |
| `--role-tts-voices` | `en-US-JennyNeural` `en-US-EricNeural` | Edge TTS voice(s), repeatable                                    |
| `--language`        | `en`                                   | Dialogue language (`zh` / `en` / `ja` / `ko` etc.)               |
| `--save-dir`        | `./audios/podcast`                     | Audio output directory                                           |
| `--category`        | `0`                                    | Category (0=unknown 1=tech 2=education 3=food 4=travel 5=code …) |
| `--is-published`    | `False`                                | When set, marks as published in D1 and prints the public URL     |

---

### Audio Only (No Database)

```bash
# Single source → generate mp3 + vtt
content-parser-tts instruct-content-tts \
    "https://en.wikipedia.org/wiki/Large_language_model"

# Chinese
content-parser-tts instruct-content-tts \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    "https://en.wikipedia.org/wiki/Large_language_model"

# Manually merge segmented audio
content-parser-tts merge-audio-files \
    audios/podcast/Large_language_model/0  audios/podcast/LLM.mp3
```

---

### Generate RSS Feed

```bash
# Generate rss.xml locally from D1 podcast data
gen-podcasts-xml gen_xml_from_d1_podcast

# Generate and upload to Cloudflare R2
gen-podcasts-xml gen_xml_from_d1_podcast --is-upload

# Or use make
make gen-rss          # generate only
make gen-rss-upload   # generate + upload to R2
```

---

### Manual Database Insert

```bash
# Upload audio + generate cover + write to D1
insert-podcast insert-podcast-to-d1 \
    ./audios/podcast/LLM.mp3 \
    "Large Language Model" \
    "weedge" \
    "en-US-EricNeural,en-US-JennyNeural" \
    --language en \
    --category 1 \
    --is-published

# Update cover art
insert-podcast update-podcast-cover-to-d1 \
    <pid> "https://example.com/cover.png"
```

---

## Recommended Edge TTS Voices

### Chinese `--language zh`

| Voice ID               | Gender | Style                            |
| ---------------------- | ------ | -------------------------------- |
| `zh-CN-YunjianNeural`  | Male   | Broadcast style                  |
| `zh-CN-YunxiNeural`    | Male   | Narrative style                  |
| `zh-CN-YunyangNeural`  | Male   | News style                       |
| `zh-CN-XiaoxiaoNeural` | Female | Natural & friendly (recommended) |
| `zh-CN-XiaoyiNeural`   | Female | Gentle & sweet                   |

### English `--language en` (default)

| Voice ID            | Gender |
| ------------------- | ------ |
| `en-US-EricNeural`  | Male   |
| `en-US-JennyNeural` | Female |

> **Note**: When `--language zh` is set without Chinese voices, the tool automatically replaces them and prints a warning with the recommended list.

---

## Supported Gemini Models

| Model ID                        | Description                    |
| ------------------------------- | ------------------------------ |
| `gemini-3-flash-preview`        | Default, Gemini 3 Flash (fast) |
| `gemini-3.1-flash-lite-preview` | Gemini 3.1 Lite                |
| `gemini-2.5-flash`              | Stable, production-ready       |
| `gemini-2.5-pro`                | Best reasoning, higher cost    |

> **Note**: `gemini-3.1-flash-preview` does not exist and will return a 404 error.

---

## Pipeline Overview

```
Source (URL / PDF)
       │
       ▼
ContentExtractor          ← Webpage / YouTube / PDF
       │
       ▼
Gemini LLM (instructor)   ← Streams structured multi-role Podcast object
       │
       ▼
Edge TTS (per-role)       ← Auto-cleans Markdown/SSML, exponential backoff retry
       │
       ▼
pydub merge mp3
       │
       ├─── SiliconFlow cover art (translate title → generate → compress)
       │
       ▼
Cloudflare R2 upload (audio + cover)
       │
       ▼
Cloudflare D1 metadata insert
```

---

## Make Commands

```bash
make help            # Show all available commands
make install         # Install the package in editable mode
make gen-podcast     # Run gen-podcast CLI (pass ARGS="..." for extra arguments)
make gen-rss         # Generate RSS feed XML from D1 podcast data
make gen-rss-upload  # Generate RSS feed XML and upload to Cloudflare R2
make build           # Build source and wheel distributions
make dist-local      # Install the built wheel locally
make publish-test    # Publish package to TestPyPI
make publish         # Publish package to PyPI
make clean           # Remove build artifacts
```

---

## Troubleshooting

| Error                                   | Cause                                                          | Solution                                                                       |
| --------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `503 UNAVAILABLE`                       | Gemini service overloaded                                      | Set `GEMINI_FALLBACK_MODEL=gemini-2.5-flash` for automatic retry with fallback |
| `404 not found`                         | Invalid model ID                                               | Check `GEMINI_MODEL`; do not use `gemini-3.1-flash-preview`                    |
| `NoAudioReceived`                       | Text contains unsupported characters or Edge TTS service issue | Tool auto-cleans and retries; skips the segment if all attempts fail           |
| `ModuleNotFoundError: jsonref`          | Missing dependency                                             | `pip install jsonref` or `pip install -e .`                                    |
| Chinese podcast opens/closes in English | Default English voices used or `--language zh` not set         | Add `--language zh --role-tts-voices zh-CN-YunjianNeural ...`                  |
