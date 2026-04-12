# gen-podcast 详细参考

## 核心模块 API

### gen_podcast.py — 端到端入口

**CLI 命令**：`python -m podcast.gen_podcast`

| 子命令 | 说明 |
|--------|------|
| `run [SOURCES...]` | 端到端：提取内容 → LLM 生成对话 → TTS → 上传 R2 → 写入 D1 |
| `get-source-type <url>` | 返回来源类型：`youtube` / `website` / 文件扩展名 |

`run` 内部流程：
1. 调用 `instruct_content_tts` 获得 `(source, extraction, audio_output_file)`
2. 用 `podcast.speakers` / `podcast.content` 组装元数据
3. 调用 `insert_podcast_to_d1`（最多重试 3 次）

### content_parser_tts.py — 内容提取 + TTS

**CLI 命令**：`python -m podcast.content_parser_tts`

| 子命令 | 说明 |
|--------|------|
| `instruct-content-tts [SOURCES...]` | 提取内容 → LLM → TTS → 合并 MP3 |
| `merge-audio-files <dir> <output.mp3>` | 合并目录下分段 MP3 |
| `instruct-role-tts` | 已有文本 → 仅 TTS（调试用） |
| `instruct-podcast-tts` | 已有文本 → 仅 TTS（调试用） |

内部流程：
1. `ContentExtractor.extract_content` → 文本
2. `instruct_podcast_tts` → 流式 `extract_models` 得到 `Podcast` 结构
3. `gen_podcast_tts_audios` → 逐角色 Edge TTS 写 `.mp3` + `.vtt`
4. `merge_audio_files` → 合并为最终 MP3

### insert_podcast.py — 上传与入库

**CLI 命令**：`python -m podcast.insert_podcast`

| 子命令 | 说明 |
|--------|------|
| `insert-podcast-to-d1` | 音频上传 R2 + 封面生成 + 写入 D1 |
| `get-podcast` | 获取播客信息 |
| `update-podcast-cover-to-d1 <pid> <url>` | 更新封面 |
| `update-podcast-audio-size-to-d1` | 更新音频大小 |
| `get-audio-duration` | 获取音频时长 |

### content_parser/table/podcast.py — LLM 核心

- `extract_models` / `extract_models_partial`：调用 Gemini 流式生成
- `Podcast` 模型：`title`, `description`, `roles: list[Role]`
- `Role` 模型：`name`, `content`
- `speakers(podcast)` → 角色名列表
- `content(podcast)` → 完整对话文本
- 自动主模型 + fallback 模型重试机制

## 结构化输出模型

```python
class Role(BaseModel):
    name: str      # 角色名
    content: str   # 该角色的台词

class Podcast(BaseModel):
    title: str
    description: str
    roles: list[Role]
```

## 内容提取器

| 提取器 | 模块 | 来源类型 |
|--------|------|----------|
| `WebsiteExtractor` | `website_extractor_instructor.py` | HTTP(S) 网页 |
| `YouTubeTranscriber` | `youtube_transcriber_instructor.py` | YouTube 视频字幕 |
| `PDFExtractor` | `pdf_extractor_instructor.py` | 本地 PDF 文件 |
| `ContentExtractor` | `content_extractor_instructor.py` | 统一入口，自动识别 |

## 支持的语言代码

`types.py` 中的 `TO_LLM_LANGUAGE` 映射：

| 代码 | 语言 |
|------|------|
| `en` | English |
| `zh` | Chinese |
| `ja` | Japanese |
| `ko` | Korean |
| `es` | Spanish |
| `fr` | French |
| `de` | German |

## 分类 ID

| ID | 分类 |
|----|------|
| 0 | 未知 |
| 1 | 科技 |
| 2 | 教育 |
| 3 | 美食 |
| 4 | 旅行 |
| 5 | 代码 |

## 重要约束

- TTS 语音数量必须与 LLM 输出的角色数量一致（默认 2 角色 2 语音）
- `--language zh` 时若使用英文语音，工具自动替换并提示
- 默认作者名为 `weedge`
- 对话轮数默认随机 20-50 轮（可通过 `ROUND_CN` 环境变量控制）
- Gemini 主模型 503 时自动降级到 `GEMINI_FALLBACK_MODEL`
