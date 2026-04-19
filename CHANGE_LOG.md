# Change Log

## v0.1.3

AI-powered podcast generation: extract content from any source, generate multi-role dialogue scripts via Gemini LLM, synthesize speech with Edge TTS — now with **word-level subtitles** for karaoke-style highlighting.

### What's New

#### Word-Level Subtitles via Gemini Audio

New `subtitle-gen` CLI and `podcast/subtitle_generator.py` module that uploads the final podcast mp3 to Gemini, requests schema-bound per-token timing, and writes 4 subtitle artifacts alongside the audio:

| File | Use case |
|---|---|
| `<stem>.words.json` | Front-end / video player per-word rendering (segments[{speaker,text,start,end,words:[...]}]) |
| `<stem>.words.vtt` | WebVTT with inline `<00:00:00.500>` karaoke time tags |
| `<stem>.words.lrc` | Enhanced LRC (A2 extension) with per-token `<mm:ss.xx>` timestamps |
| `<stem>.srt` | Classic sentence-level SRT |

Tokenization adapts to language:
- **CJK** (`zh` / `ja` / `ko`): 2–5-character natural phrases
- **Space-separated** (`en` / `es` / `fr` / …): one token per word

Long audio is automatically split into chunks (default 300 s, `SUBTITLE_CHUNK_SEC` / `--chunk-sec`) to avoid Gemini `MAX_TOKENS` truncation; chunk timestamps are re-offset and merged. `max_output_tokens=65535` is set explicitly, and `finish_reason=MAX_TOKENS` produces an actionable error.

Standalone use:
```bash
subtitle-gen generate audios/podcast/foo.mp3 --language zh
# or via make
make subtitle-gen AUDIO=audios/podcast/foo.mp3 LANG=zh
```

Integrated into `gen-podcast run` as **opt-in** via `--subtitles` (default off, safe for databases that have not yet been migrated). Override the model with `--subtitle-model`.

#### D1 Schema Extension

Four new columns on `podcast` to store R2 URLs of the generated subtitle artifacts:

```sql
ALTER TABLE podcast ADD COLUMN subtitle_json_url text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_vtt_url  text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_lrc_url  text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_srt_url  text DEFAULT "";
```

Full schema + migration lives in `podcast/sql/podcast.sql` and the comment block at the top of `podcast/insert_podcast.py`. New `insert-podcast update-podcast-subtitles-to-d1` CLI backfills URLs on existing rows.

#### Shared LLM Retry Helpers

`podcast/_llm_retry.py` centralizes Gemini transient-error handling (`is_transient_llm_error`, `invoke_with_transient_retry`, `stream_with_transient_retry`); text (`content_parser/table/podcast.py`) and audio (`subtitle_generator.py`) paths now share identical backoff semantics. Upload and `generate_content` are both wrapped so `ConnectTimeout` during file upload retries cleanly.

### Fixes

- **Last role of a podcast was silently dropped when the Gemini partial stream ended on an empty-content role** (`content_parser_tts.py`). The `duplicate`-overwrite mechanism relies on the next role's yield to refresh the previous one's content — the last role never had a "next," so a truncated or empty final utterance (e.g. `Weedge: 再见，下次见！`) was lost. Added a post-loop fallback that either appends (`[final-append]`) or overwrites (`[final-fix]`) the final role using the stream's final state.

### Config

New environment variables (both optional, sensible defaults):

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_SUBTITLE_MODEL` | `gemini-2.5-flash` | Audio-capable model for the subtitle pass |
| `SUBTITLE_CHUNK_SEC` | `300` | Chunk length (s) for long-audio splitting |

### Docs

- `CLAUDE.md` added — architecture, pipeline, commands, D1 schema. Read first when operating this repo with Claude Code.
- `README.md` / `README_CN.md` updated — new feature row, env table row, `run` options, standalone Word-Level Subtitles section, make target, manual backfill CLI.
- `makefile` — new `make subtitle-gen AUDIO=... [LANG=...] [ARGS="..."]` target.

### Install

```bash
pip install gen-podcast==0.1.3
```

Existing D1 databases need the four `ALTER TABLE` statements above before running `gen-podcast run` with subtitles enabled (or pass `--no-subtitles`).

### Files Changed

| File | Change |
|---|---|
| `podcast/subtitle_generator.py` | **new** — Gemini audio → word-level subtitle generation + CLI |
| `podcast/_llm_retry.py` | **new** — shared Gemini retry helpers |
| `podcast/sql/podcast.sql` | **new** — D1 schema + migration SQL |
| `CLAUDE.md` | **new** — Claude Code guidance |
| `podcast/gen_podcast.py` | `--subtitles / --no-subtitles`, `--subtitle-model`; auto subtitle generation + R2 upload |
| `podcast/insert_podcast.py` | 4 subtitle URL columns; `update-podcast-subtitles-to-d1` CLI |
| `podcast/content_parser_tts.py` | post-loop final-role fallback |
| `podcast/content_parser/table/podcast.py` | retry logic extracted to `_llm_retry` |
| `makefile`, `README.md`, `README_CN.md`, `.env.example`, `pyproject.toml` | version bump, docs, new target, new env vars, new CLI entry |
