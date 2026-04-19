import os
import re
import logging
import asyncio
from datetime import datetime
import shutil
from typing import Generator, List, Union

from pydantic import ValidationError
from pydub import AudioSegment
import edge_tts
from edge_tts.communicate import Communicate, remove_incompatible_characters
from edge_tts.exceptions import NoAudioReceived, WebSocketError
import typer

from .content_parser.content_extractor_instructor import ContentExtractor
from .content_parser.table import podcast

app = typer.Typer()

LANGUAGE_VOICE_PREFIX: dict[str, str] = {
    "zh": "zh-CN-",
    "en": "en-US-",
    "ja": "ja-JP-",
    "ko": "ko-KR-",
}

ZH_VOICES_HINT = """
当 --language zh 时，请使用中文语音。推荐列表：

  女声 (Female):
    zh-CN-XiaoxiaoNeural   （晓晓，最常用）
    zh-CN-XiaoyiNeural     （晓伊）

  男声 (Male):
    zh-CN-YunjianNeural    （云健，播音风格）
    zh-CN-YunxiNeural      （云希，叙述风格）
    zh-CN-YunyangNeural    （云扬，新闻风格）
    zh-CN-YunxiaNeural     （云夏）

示例：
  --role-tts-voices zh-CN-YunjianNeural --role-tts-voices zh-CN-XiaoxiaoNeural
"""


def _check_voice_language_match(
    role_tts_voices: List[str], language: str
) -> List[str]:
    """检查 voice 与 language 是否匹配；不匹配时发出警告并自动替换为对应语言的默认语音。"""
    prefix = LANGUAGE_VOICE_PREFIX.get(language)
    if prefix is None:
        return list(role_tts_voices)

    mismatched = [v for v in role_tts_voices if not v.startswith(prefix)]
    if not mismatched:
        return list(role_tts_voices)

    if language == "zh":
        defaults = ["zh-CN-YunjianNeural", "zh-CN-XiaoxiaoNeural"]
        logging.warning(
            "语音 %s 与 --language zh 不匹配，已自动切换为 %s%s",
            mismatched,
            defaults,
            ZH_VOICES_HINT,
        )
    elif language == "en":
        defaults = ["en-US-EricNeural", "en-US-JennyNeural"]
        logging.warning(
            "语音 %s 与 --language en 不匹配，已自动切换为 %s",
            mismatched,
            defaults,
        )
    else:
        logging.warning("语音 %s 前缀与 --language %s（期望 %s）不匹配", mismatched, language, prefix)
        return list(role_tts_voices)

    result: list[str] = []
    di = 0
    for v in role_tts_voices:
        if v.startswith(prefix):
            result.append(v)
        else:
            result.append(defaults[di % len(defaults)])
            di += 1
    return result


def _coerce_role(role: podcast.Role | dict) -> podcast.Role | None:
    """create_partial 流式里 roles 常为 dict，且会先出现只有 name、尚无 content 的片段；凑齐后再生成 Role。"""
    if isinstance(role, podcast.Role):
        if not (role.content or "").strip():
            return None
        return role
    if not isinstance(role, dict):
        return None
    raw = role.get("content")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return podcast.Role.model_validate(role)
    except ValidationError:
        return None


_STRIP_SSML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_STRIP_MARKDOWN_RE = re.compile(r"[*_#`~\[\](){}|>]")
_COLLAPSE_SPACES_RE = re.compile(r"[ \t]{2,}")
_COLLAPSE_NEWLINES_RE = re.compile(r"\n{3,}")


def _sanitize_for_edge_tts(text: str) -> str:
    """去掉 LLM 残留的 markdown / SSML 标签 / 特殊符号后再给 Edge TTS。"""
    if not text or not str(text).strip():
        return ""
    t = str(text)
    t = remove_incompatible_characters(t)
    t = _STRIP_SSML_TAG_RE.sub("", t)
    t = _STRIP_MARKDOWN_RE.sub("", t)
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace("—", ", ").replace("–", ", ")
    t = _COLLAPSE_SPACES_RE.sub(" ", t)
    t = _COLLAPSE_NEWLINES_RE.sub("\n\n", t)
    return t.strip()


def _fallback_text_chunks(text: str) -> list[str]:
    """整段 TTS 失败时：先按段落，再对超长单段按近似词边界切分。"""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) > 1:
        return parts
    single = parts[0] if parts else text.strip()
    if len(single) <= 3500:
        return [single] if single else []
    chunk_size = 2800
    out: list[str] = []
    start = 0
    n = len(single)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            sp = single.rfind(" ", start, end)
            if sp <= start:
                sp = single.rfind("\n", start, end)
            if sp > start:
                end = sp + 1
        piece = single[start:end].strip()
        if piece:
            out.append(piece)
        next_start = end if end > start else start + 1
        if next_start <= start:
            break
        start = next_start
    return out if out else ([single] if single else [])


async def _communicate_stream_to_files(
    text: str,
    output_file: str,
    voice: str,
    *,
    rate: str = "+15%",
    boundary: str = "SentenceBoundary",
) -> None:
    communicate = Communicate(text, voice, rate=rate, boundary=boundary)
    submaker = edge_tts.SubMaker()
    webvtt_file = ".".join(output_file.split(".")[:-1]) + ".vtt"
    with open(output_file, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)
    with open(webvtt_file, "w", encoding="utf-8") as file:
        file.write(submaker.get_srt())


async def edge_tts_conversion(
    text_chunk: str, output_file: str, voice: str, boundary: str = "SentenceBoundary"
):
    text = _sanitize_for_edge_tts(text_chunk)
    if not text:
        logging.warning("跳过 TTS：文本在清理后为空")
        return

    # 重试 + 参数降级（NoAudioReceived 常见于瞬时失败或 boundary/rate 不兼容）
    attempts: list[tuple[str, str, str]] = [
        ("+15%", boundary, "默认"),
        ("+15%", "WordBoundary", "WordBoundary"),
        ("+0%", "SentenceBoundary", "rate=0"),
        ("+0%", "WordBoundary", "rate=0+WordBoundary"),
    ]
    last_err: Exception | None = None
    for rate, bd, label in attempts:
        for retry in range(3):
            try:
                await _communicate_stream_to_files(
                    text, output_file, voice, rate=rate, boundary=bd
                )
                if label != "默认" or retry > 0:
                    logging.info("TTS 成功（%s，第 %s 次尝试）", label, retry + 1)
                return
            except (NoAudioReceived, WebSocketError) as e:
                last_err = e
                extra = f" | text[:100]={text[:100]!r}" if retry == 0 and label == "默认" else ""
                logging.warning("Edge TTS 失败 (%s, 尝试 %s/3): %s%s", label, retry + 1, e, extra)
                await asyncio.sleep(1.0 * (2**retry))
            except Exception:
                raise

    # 按段落 / 超长切分再合并（避免单一大段偶发无音频）
    parts = _fallback_text_chunks(text)
    if len(parts) > 1:
        logging.info("TTS 整段失败，改为按 %s 段分段合成", len(parts))
        segments: list[AudioSegment] = []
        part_files: list[str] = []
        try:
            for i, part in enumerate(parts):
                pf = f"{output_file}.part{i}.mp3"
                part_files.append(pf)
                await _communicate_stream_to_files(
                    part, pf, voice, rate="+0%", boundary="WordBoundary"
                )
                segments.append(AudioSegment.from_file(pf, format="mp3"))
            merged = segments[0]
            for seg in segments[1:]:
                merged += seg
            merged.export(output_file, format="mp3")
            logging.info("分段 TTS 已合并至 %s", output_file)
            return
        finally:
            for pf in part_files:
                if os.path.isfile(pf):
                    try:
                        os.remove(pf)
                    except OSError:
                        pass

    logging.error(
        "Edge TTS 所有参数/分段/重试均失败，跳过该段文本 (前 200 字): %s",
        text[:200],
    )
    return


async def gen_role_tts_audios(
    data_models: Generator[podcast.Role, None, None],
    save_dir: str,
    role_tts_voices: List[str],
):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    i = 0
    for role in data_models:
        role = _coerce_role(role)
        if role is None:
            continue
        output_file = os.path.join(save_dir, f"{i}_{role.name}.mp3")
        voice = role_tts_voices[i % len(role_tts_voices)]
        print(f"{i}. {role.name}: {role.content} speaker:{voice} \n")
        i += 1
        await edge_tts_conversion(
            role.content,
            output_file,
            voice,
        )
    return 1 if i > 0 else 0


async def gen_podcast_tts_audios(
    data_models: Generator[podcast.Podcast, None, None],
    save_dir: str,
    role_tts_voices: List[str],
):
    podcast_index, role_index = (0, 0)
    pre_role = ""
    pre_cn, cur_cn = (0, 0)
    title = ""
    description = ""
    extraction = None
    p_save_dir = os.path.join(save_dir, str(podcast_index))
    for extraction in data_models:
        if title == "" and extraction.description:
            title = extraction.title
            print(f"title:{title}\n")
        if description == "" and extraction.roles:
            description = extraction.description
            print(f"description:{description}\n")
        if not extraction.roles:
            continue
        p_save_dir = os.path.join(save_dir, str(podcast_index))
        if not os.path.exists(p_save_dir):
            os.makedirs(p_save_dir)
        # print(f"----------podcast {podcast_index}----{len(extraction.roles)}---------")

        pre_cn = cur_cn
        cur_cn = len(extraction.roles)
        if pre_cn == cur_cn:
            # print(f"pre_cn == cur_cn :{pre_cn} continue")
            continue
        if pre_cn > cur_cn:
            # just use the first podcast, break
            break
            podcast_index += 1
            pre_cn = 1
            role_index = 0

        # print(pre_cn, extraction.roles, extraction.roles[pre_cn - 1:])
        for role in extraction.roles[pre_cn - 1:]:
            role = _coerce_role(role)
            if role is None:
                continue
            if pre_role == role.name:
                logging.warning(f"duplicate {role.name}: {role.content}")
                # remove pre tts audio content
                pre_audio_file = os.path.join(p_save_dir, f"{role_index - 1}_{role.name}.mp3")
                if os.path.exists(pre_audio_file):
                    os.remove(pre_audio_file)
                    # logging.warning(f"remove {pre_audio_file}")
                pre_vtt_file = os.path.join(p_save_dir, f"{role_index - 1}_{role.name}.vtt")
                if os.path.exists(pre_vtt_file):
                    os.remove(pre_vtt_file)
                    # logging.warning(f"remove {pre_vtt_file}")
                role_index -= 1

            output_file = os.path.join(p_save_dir, f"{role_index}_{role.name}.mp3")
            voice = role_tts_voices[role_index % len(role_tts_voices)]
            print(f"{role_index}. {role.name}: {role.content} speaker:{voice} \n")
            pre_role = role.name
            role_index += 1
            await edge_tts_conversion(role.content, output_file, voice)

    # 流结束后兜底：最后一条 role 的 content 补录 / 覆盖。
    # `duplicate` 覆盖逻辑依赖"下一条 role 的出现"来重做上一条；流末端不存在"下一条"，
    # 于是上一轮 yield 中若最后一条 content 尚未完整就可能留下截断音频（或被 _coerce_role
    # 判空跳过），需要在这里显式重做。
    if extraction is not None and extraction.roles:
        last_role = _coerce_role(extraction.roles[-1])
        if last_role is not None:
            if not os.path.exists(p_save_dir):
                os.makedirs(p_save_dir)
            write_idx = role_index - 1 if pre_role == last_role.name else role_index
            prev_audio = os.path.join(p_save_dir, f"{write_idx}_{last_role.name}.mp3")
            prev_vtt = os.path.join(p_save_dir, f"{write_idx}_{last_role.name}.vtt")
            existed = os.path.isfile(prev_audio)
            for f in (prev_audio, prev_vtt):
                if os.path.isfile(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            voice = role_tts_voices[write_idx % len(role_tts_voices)]
            tag = "final-fix" if existed else "final-append"
            print(f"[{tag}] {write_idx}. {last_role.name}: {last_role.content} speaker:{voice}\n")
            await edge_tts_conversion(last_role.content, prev_audio, voice)
            pre_role = last_role.name
            if not existed:
                role_index += 1

    # print(extraction)
    return extraction



@app.command("merge_audio_files")
def merge_audio_files(input_dir: str, output_file: str) -> None:
    try:
        # Function to sort filenames naturally
        def natural_sort_key(filename: str) -> List[Union[int, str]]:
            return [int(text) if text.isdigit() else text for text in re.split(r"(\d+)", filename)]

        combined = AudioSegment.empty()
        audio_files = sorted(
            [f for f in os.listdir(input_dir) if f.endswith(".mp3")], key=natural_sort_key
        )
        logging.info(f"sorted audio_files: {audio_files}")
        for file in audio_files:
            file_path = os.path.join(input_dir, file)
            combined += AudioSegment.from_file(file_path, format="mp3")

        combined.export(output_file, format="mp3")
        logging.info(f"Merged audio saved to {output_file}")
    except Exception as e:
        logging.error(f"Error merging audio files: {str(e)}")
        raise


@app.command()
def instruct_role_tts(
    content: str,
    tmp_dir: str,
    role_tts_voices: List[str] = ["en-US-JennyNeural", "en-US-EricNeural"],
    language: str = "en",
):
    role_tts_voices = _check_voice_language_match(role_tts_voices, language)
    data_models = podcast.extract_role_models_iterable(content, language=language)
    return asyncio.run(gen_role_tts_audios(data_models, tmp_dir, role_tts_voices))


@app.command()
def instruct_podcast_tts(
    content: str,
    tmp_dir: str,
    role_tts_voices: List[str] = ["en-US-JennyNeural", "en-US-EricNeural"],
    language: str = "en",
):
    role_tts_voices = _check_voice_language_match(role_tts_voices, language)
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    data_models = podcast.extract_models(content, language=language)
    return asyncio.run(gen_podcast_tts_audios(data_models, tmp_dir, role_tts_voices))


def instruct_content_tts(
    sources: List[str],
    role_tts_voices: List[str] = ["en-US-JennyNeural", "en-US-EricNeural"],
    language: str = "en",
    save_dir: str = "./audios/podcast",
) -> list:
    role_tts_voices = _check_voice_language_match(role_tts_voices, language)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    extractor = ContentExtractor()
    res = []
    for source in sources:
        try:
            content = extractor.extract_content(source)
            logging.info(f"{source} extracted content done")
            now = datetime.now()
            formatted_time = now.strftime("%Y-%m-%d_%H-%M-%S")
            output_file = os.path.join(save_dir, f"{extractor.file_name}_{formatted_time}.mp3")
            tmp_dir = os.path.join(save_dir, extractor.file_name)
            extraction = instruct_podcast_tts(content, tmp_dir, role_tts_voices, language)
            p_tmp_dir = os.path.join(tmp_dir, "0")
            merge_audio_files(input_dir=p_tmp_dir, output_file=output_file)
            res.append((source, extraction, output_file))
        except Exception as e:
            logging.error(f"An error occurred while processing {source}: {str(e)}", exc_info=True)

    return res


@app.command("instruct-content-tts")
def instruct_content_tts_cli(
    ctx: typer.Context,
    sources: List[str],
    role_tts_voices: List[str] = ["en-US-JennyNeural", "en-US-EricNeural"],
    language: str = "en",
    save_dir: str = "./audios/podcast",
) -> list:
    cmd = (ctx.command.name or "").replace("_", "-")
    sources = [s for s in sources if s.replace("_", "-") != cmd]
    return instruct_content_tts(
        sources,
        role_tts_voices=role_tts_voices,
        language=language,
        save_dir=save_dir,
    )


r"""
python -m podcast.content_parser_tts instruct-content-tts \
    "https://en.wikipedia.org/wiki/Large_language_model"

python -m podcast.content_parser_tts instruct-content-tts \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    "https://en.wikipedia.org/wiki/Large_language_model" \
    "https://www.youtube.com/watch?v=aR6CzM0x-g0" \
    "/path/to/paper.pdf"

python -m podcast.content_parser_tts merge_audio_files \
    audios/podcast/2401.02669/0  audios/podcast/2401.02669.mp3
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[
            logging.StreamHandler()],
    )
    app()
