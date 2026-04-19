import os
import time
import logging
from typing import List
from urllib.parse import urlparse

import typer

from .aws.upload import r2_upload
from .content_parser.table import podcast
from .content_parser_tts import instruct_content_tts
from .insert_podcast import insert_podcast_to_d1
from . import subtitle_generator as sg


app = typer.Typer()


def _expand_source_path(source: str) -> str:
    return os.path.expanduser(source.strip())


def is_url(source: str) -> bool:
    if os.path.isfile(_expand_source_path(source)):
        return False
    try:
        # If the source doesn't start with a scheme, add 'https://'
        if not source.startswith(("http://", "https://")):
            source = "https://" + source

        result = urlparse(source)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def is_file(source: str) -> bool:
    return os.path.isfile(_expand_source_path(source))


@app.command("get_source_type")
def get_source_type(source: str):
    src_type = ""
    isUrl = is_url(source)
    if isUrl:
        if any(pattern in source for pattern in ["youtube.com", "youtu.be"]):
            src_type = "youtube"
        else:
            src_type = "website"
    elif is_file(source):
        sp = source.split(".")
        src_type = sp[-1] if len(sp) > 0 else "file"

    return src_type


@app.command("run")
def run(
    ctx: typer.Context,
    sources: List[str],
    role_tts_voices: List[str] = ["en-US-JennyNeural", "en-US-EricNeural"],
    language: str = "en",
    save_dir: str = "./audios/podcast",
    category: int = 0,
    is_published: bool = False,
    subtitles: bool = typer.Option(
        False, "--subtitles/--no-subtitles", help="生成 Gemini 逐字字幕并上传 R2/写入 D1"
    ),
    subtitle_model: str = typer.Option(
        "", help="覆盖 GEMINI_SUBTITLE_MODEL"
    ),
):
    cmd = (ctx.command.name or "").replace("_", "-")
    sources = [s for s in sources if s.replace("_", "-") != cmd]

    data_list = instruct_content_tts(
        sources,
        role_tts_voices=role_tts_voices,
        language=language,
        save_dir=save_dir,
    )
    for data in data_list:
        print(data)
        source = data[0]
        extraction: podcast.Podcast = data[1]
        audio_output_file = data[2]

        speakers = podcast.speakers(extraction, role_tts_voices)
        logging.info(f"speakers:{speakers}")
        audio_content = podcast.content(extraction, "text")
        logging.info(f"audio_content:{audio_content}")

        subtitle_urls = {"json": "", "vtt": "", "lrc": "", "srt": ""}
        if subtitles:
            try:
                subtitle_urls = _gen_and_upload_subtitles(
                    audio_output_file,
                    language=language,
                    script_hint=audio_content,
                    model=subtitle_model or None,
                )
            except Exception as e:  # noqa: BLE001
                logging.error(
                    "subtitle generation/upload failed, continuing without subtitles: %s",
                    e,
                    exc_info=True,
                )

        retries = 0
        max_retries = 3
        while retries < max_retries:
            try:
                insert_podcast_to_d1(
                    audio_output_file,
                    extraction.title,
                    "weedge",
                    ",".join(speakers),
                    description=extraction.description,
                    audio_content=audio_content,
                    is_published=is_published,
                    category=category,
                    source=source,
                    language=language,
                    subtitle_json_url=subtitle_urls.get("json", ""),
                    subtitle_vtt_url=subtitle_urls.get("vtt", ""),
                    subtitle_lrc_url=subtitle_urls.get("lrc", ""),
                    subtitle_srt_url=subtitle_urls.get("srt", ""),
                )
                break
            except Exception as e:
                retries += 1
                logging.warning(
                    f"insert_podcast_to_d1 failed, retrying ({retries}/{max_retries}): {e}"
                )
                time.sleep(1)
                if retries == max_retries:
                    logging.error("Max retries reached, insert_podcast_to_d1 failed.")
                    raise


def _gen_and_upload_subtitles(
    audio_path: str,
    language: str,
    script_hint: str,
    model: str | None = None,
) -> dict[str, str]:
    """Transcribe audio via Gemini, write 4 subtitle files next to it, upload each to R2.

    Returns {"json": url, "vtt": url, "lrc": url, "srt": url}. An empty string is
    left for any format whose upload failed; the mp3 insert flow should still proceed.
    """
    subs = sg.generate_word_level_subtitles(
        audio_path,
        language=language,
        script_hint=script_hint or None,
        model=model,
    )
    local_paths = sg.write_all(subs, audio_path=audio_path)
    urls: dict[str, str] = {}
    for fmt, path in local_paths.items():
        try:
            urls[fmt] = r2_upload("podcast", path)
        except Exception as e:  # noqa: BLE001
            logging.error("R2 upload of %s subtitle %s failed: %s", fmt, path, e)
            urls[fmt] = ""
    logging.info("subtitle urls: %s", urls)
    return urls


r"""
python -m podcast.gen_podcast run \
    "https://en.wikipedia.org/wiki/Large_language_model"

python -m podcast.gen_podcast run \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --role-tts-voices zh-CN-YunjianNeural \
    --category 1 \
    --language zh \
    --is-published \
    "https://www.youtube.com/watch?v=aR6CzM0x-g0" \
    "https://en.wikipedia.org/wiki/Large_language_model" \
    "/path/to/paper.pdf

"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[
            logging.StreamHandler()],
    )
    app()
