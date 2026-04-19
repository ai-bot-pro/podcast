![aipodcast](https://github.com/user-attachments/assets/b78dd807-9e27-4f66-84c0-2a78b9b14388)

# AI Bot Pro — Podcast

<p align="center">
  <a href="https://pypi.org/project/gen-podcast/"><img src="https://img.shields.io/pypi/v/gen-podcast?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/gen-podcast/"><img src="https://img.shields.io/pypi/pyversions/gen-podcast?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/ai-bot-pro/podcast/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://weedge.github.io/about/"><img src="https://img.shields.io/badge/Built%20by-weedge-blueviolet?style=for-the-badge" alt="Built by weedge"></a>
</p>

[English](./README.md) | [中文](./README_CN.md)

AI 驱动的播客生成工具：从任意内容（网页、YouTube、PDF）自动提取文本 → Gemini LLM 生成多角色对话脚本 → Edge TTS 语音合成 → Cloudflare R2 存储 + Cloudflare D1 数据库入库。

- AI Podcast: https://podcast-997.pages.dev/
- AI Podcast UI & Cloudflare Worker: https://github.com/ai-bot-pro/react-nextjs-web-podcast

---

## 功能概览

| 步骤          | 说明                                                            |
| ------------- | --------------------------------------------------------------- |
| **内容抓取**  | 支持网页（BeautifulSoup）、YouTube（字幕/转写）、PDF（PyMuPDF） |
| **脚本生成**  | Gemini（`google-genai` + `instructor`）流式生成多角色播客对话   |
| **语音合成**  | Microsoft Edge TTS，支持中英日韩等多语言，带指数退避重试        |
| **封面生成**  | SiliconFlow AI 图像生成，自动压缩后上传 Cloudflare R2           |
| **逐字字幕**  | Gemini 音频理解给出 token 级时间戳，输出 JSON / WebVTT（卡拉OK `<time>` 标签）/ 增强 LRC / SRT |
| **存储/入库** | Cloudflare R2（音频/图片/字幕）+ Cloudflare D1（元数据）        |
| **RSS 订阅**  | 从 D1 生成 Apple Podcasts 兼容的 RSS XML，可选上传至 R2         |

---

## 目录结构

```
podcast/
├── pyproject.toml
├── .env.example
├── podcast/
│   ├── gen_podcast.py              # 端到端入口（CLI）
│   ├── gen_podcasts_xml.py         # 从 D1 生成 RSS 订阅源
│   ├── content_parser_tts.py       # 内容提取 + TTS
│   ├── subtitle_generator.py       # Gemini 音频 → 逐字字幕
│   ├── insert_podcast.py           # 上传 R2 + 写入 D1
│   ├── _llm_retry.py               # Gemini 瞬时错误重试工具
│   ├── audio_length.py
│   ├── image_compression.py
│   ├── siliconflow_api.py
│   ├── aws/
│   │   └── upload.py               # Cloudflare R2（boto3）
│   ├── cloudflare/
│   │   └── rest_api.py             # D1 REST API
│   └── content_parser/
│       ├── types.py                # 语言代码映射
│       ├── content_extractor_instructor.py
│       ├── pdf_extractor_instructor.py
│       ├── website_extractor_instructor.py
│       ├── youtube_transcriber_instructor.py
│       └── table/
│           └── podcast.py          # LLM 提示词 + 结构化输出
└── audios/                         # 生成的音频（已 gitignore）
```

---

## 安装

```bash
# 建议 Python 3.11+
pip install gen-podcast

# 或从源码安装（开发模式）
cd podcast
make install   # 等同于: pip install -e .
```

---

## 环境变量配置

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
```

| 变量                    | 说明                                                          |
| ----------------------- | ------------------------------------------------------------- |
| `GOOGLE_API_KEY`        | Google Gemini API 密钥                                        |
| `GEMINI_MODEL`          | 模型 ID，默认 `gemini-3-flash-preview`（不含 `models/` 前缀） |
| `GEMINI_FALLBACK_MODEL` | 503 过载时自动降级的备用模型（可选，如 `gemini-2.5-flash`）   |
| `GEMINI_SUBTITLE_MODEL` | 用于逐字字幕的音频模型，默认 `gemini-2.5-flash`               |
| `GEMINI_MAX_RETRIES`    | LLM 重试次数，默认 `6`                                        |
| `GEMINI_RETRY_BASE_SEC` | 重试基础等待秒数（指数退避），默认 `2`                        |
| `ROUND_CN`              | 播客对话轮数（可选，默认随机 20–50）                          |
| `PODCAST_D1_DB_ID`      | Cloudflare D1 数据库 ID                                       |
| `CLOUDFLARE_API_KEY`    | Cloudflare API Token                                          |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账号 ID                                            |
| `CLOUDFLARE_ACCESS_KEY` | R2 Access Key                                                 |
| `CLOUDFLARE_SECRET_KEY` | R2 Secret Key                                                 |
| `CLOUDFLARE_REGION`     | R2 区域，默认 `apac`                                          |
| `S3_BUCKET_URL`         | R2 公开访问基础 URL                                           |
| `SILICONCLOUD_API_KEY`  | SiliconFlow API 密钥（封面生成）                              |

---

## 快速使用

### 端到端生成（推荐）

```bash
# 英文播客
gen-podcast run \
    "https://en.wikipedia.org/wiki/Large_language_model"

# 中文播客（指定中文语音）
gen-podcast run \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    --category 1 \
    "https://en.wikipedia.org/wiki/Large_language_model"

# 多来源 + 发布到线上
gen-podcast run \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    --category 1 \
    --is-published \
    "https://www.youtube.com/watch?v=aR6CzM0x-g0" \
    "https://en.wikipedia.org/wiki/Large_language_model" \
    "/path/to/paper.pdf"

# 或使用 make（通过 ARGS 传递额外参数）
make gen-podcast ARGS="--language zh https://en.wikipedia.org/wiki/Large_language_model"
```

`run` 参数说明：

| 参数                | 默认值                                 | 说明                                                |
| ------------------- | -------------------------------------- | --------------------------------------------------- |
| `SOURCES`           | —                                      | 一个或多个来源（网页 URL / YouTube URL / PDF 路径） |
| `--role-tts-voices` | `en-US-JennyNeural` `en-US-EricNeural` | Edge TTS 语音，可重复                               |
| `--language`        | `en`                                   | 对话语言（`zh` / `en` / `ja` / `ko` 等）            |
| `--save-dir`        | `./audios/podcast`                     | 音频输出目录                                        |
| `--category`        | `0`                                    | 分类（0=未知 1=科技 2=教育 3=美食 4=旅行 5=代码 …） |
| `--is-published`    | `False`                                | 设置后写入 D1 时标记为已发布，并打印访问链接        |
| `--subtitles` / `--no-subtitles` | `False`                   | 启用时通过 Gemini 生成逐字字幕，上传 R2 并写入 D1（默认关闭，按需加 `--subtitles`） |
| `--subtitle-model`  | `""`                                   | 仅字幕阶段覆盖 `GEMINI_SUBTITLE_MODEL`              |

---

### 仅生成音频（不入库）

```bash
# 单条来源 → 生成 mp3 + vtt
content-parser-tts instruct-content-tts \
    "https://en.wikipedia.org/wiki/Large_language_model"

# 中文
content-parser-tts instruct-content-tts \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    "https://en.wikipedia.org/wiki/Large_language_model"

# 手动合并分段音频
content-parser-tts merge-audio-files \
    audios/podcast/Large_language_model/0  audios/podcast/LLM.mp3
```

---

### 生成 RSS 订阅源

```bash
# 从 D1 播客数据生成 rss.xml
gen-podcasts-xml gen_xml_from_d1_podcast

# 生成并上传到 Cloudflare R2
gen-podcasts-xml gen_xml_from_d1_podcast --is-upload

# 或使用 make
make gen-rss          # 仅生成
make gen-rss-upload   # 生成 + 上传至 R2
```

---

### 手动入库

```bash
# 上传音频 + 生成封面 + 写入 D1
insert-podcast insert-podcast-to-d1 \
    ./audios/podcast/LLM.mp3 \
    "大型语言模型" \
    "weedge" \
    "zh-CN-YunjianNeural,zh-CN-XiaoxiaoNeural" \
    --language zh \
    --category 1 \
    --is-published

# 更新封面
insert-podcast update-podcast-cover-to-d1 \
    <pid> "https://example.com/cover.png"

# 为已存在的播客回填字幕 URL
insert-podcast update-podcast-subtitles-to-d1 \
    <pid> \
    --subtitle-json-url https://.../foo.words.json \
    --subtitle-vtt-url  https://.../foo.words.vtt \
    --subtitle-lrc-url  https://.../foo.words.lrc \
    --subtitle-srt-url  https://.../foo.srt
```

---

### 逐字字幕（Gemini Audio）

将最终合并的 mp3 交给 Gemini 转写，输出 4 份字幕文件（与音频同目录）：`<stem>.words.json`、`<stem>.words.vtt`（WebVTT 内联 `<00:00:00.500>` 卡拉OK 时间标签）、`<stem>.words.lrc`（A2 增强 LRC，逐词时间戳）、`<stem>.srt`（句子级）。中日韩语言按 2–5 字短语切 token，英文等空格分词语言按词切。

```bash
# 独立使用：为任意 mp3 生成字幕
subtitle-gen generate audios/podcast/LLM.mp3 --language zh

# 可选：同时提供对话稿辅助对齐
subtitle-gen generate audios/podcast/LLM.mp3 \
    --language zh \
    --script-file audios/podcast/LLM.txt \
    --output-dir /tmp/subs

# 只生成特定格式
subtitle-gen generate audios/podcast/LLM.mp3 --formats json --formats vtt

# 或使用 make（AUDIO 必填，LANG 默认 en）
make subtitle-gen AUDIO=audios/podcast/LLM.mp3 LANG=zh
make subtitle-gen AUDIO=audios/podcast/LLM.mp3 LANG=zh ARGS="--output-dir /tmp/subs"
```

`gen-podcast run` 默认**不启用**字幕：需要时显式加 `--subtitles`，生成的 4 份文件会自动上传 R2，URL 写入 D1 的 `subtitle_json_url` / `subtitle_vtt_url` / `subtitle_lrc_url` / `subtitle_srt_url` 列。启用前，已有 D1 库需一次性迁移：

```sql
ALTER TABLE podcast ADD COLUMN subtitle_json_url text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_vtt_url  text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_lrc_url  text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_srt_url  text DEFAULT "";
```

---

## Edge TTS 推荐语音

### 中文 `--language zh`

| 语音 ID                | 性别 | 风格             |
| ---------------------- | ---- | ---------------- |
| `zh-CN-YunjianNeural`  | 男   | 播音风格         |
| `zh-CN-YunxiNeural`    | 男   | 叙述风格         |
| `zh-CN-YunyangNeural`  | 男   | 新闻风格         |
| `zh-CN-XiaoxiaoNeural` | 女   | 自然亲切（推荐） |
| `zh-CN-XiaoyiNeural`   | 女   | 温柔甜美         |

### 英文 `--language en`（默认）

| 语音 ID             | 性别 |
| ------------------- | ---- |
| `en-US-EricNeural`  | 男   |
| `en-US-JennyNeural` | 女   |

> **注意**：`--language zh` 时若未指定中文语音，工具会自动替换并打印提示。

---

## 支持的 Gemini 模型

| 模型 ID                         | 说明                           |
| ------------------------------- | ------------------------------ |
| `gemini-3-flash-preview`        | 默认，Gemini 3 Flash（速度快） |
| `gemini-3.1-flash-lite-preview` | Gemini 3.1 轻量版              |
| `gemini-2.5-flash`              | 稳定版，适合生产               |
| `gemini-2.5-pro`                | 最强推理，成本较高             |

> **注意**：不存在 `gemini-3.1-flash-preview`，设置后会报 404。

---

## 核心流程

```
来源（URL / PDF）
       │
       ▼
ContentExtractor          ← 网页 / YouTube / PDF
       │
       ▼
Gemini LLM (instructor)   ← 流式生成多角色对话 Podcast 结构
       │
       ▼
Edge TTS (逐角色合成)      ← 自动清理 Markdown/SSML，指数退避重试
       │
       ▼
pydub 合并 mp3
       │
       ├─── SiliconFlow 生成封面（翻译标题 → 生成 → 压缩）
       │
       ├─── Gemini 音频 → 逐字字幕（json / vtt / lrc / srt）[需 --subtitles 启用]
       │
       ▼
Cloudflare R2 上传（音频 + 封面 + 字幕）
       │
       ▼
Cloudflare D1 写入元数据（含字幕 URL）
```

---

## Make 命令

```bash
make help            # 显示所有可用命令
make install         # 以开发模式安装包
make gen-podcast     # 运行 gen-podcast CLI（通过 ARGS="..." 传递额外参数）
make gen-rss         # 从 D1 播客数据生成 RSS 订阅源
make gen-rss-upload  # 生成 RSS 订阅源并上传至 Cloudflare R2
make subtitle-gen    # 通过 Gemini 为音频生成逐字字幕（AUDIO=path [LANG=zh] [ARGS="..."]）
make build           # 构建源码包和 wheel 包
make dist-local      # 本地安装构建的 wheel 包
make publish-test    # 发布到 TestPyPI
make publish         # 发布到 PyPI
make clean           # 清理构建产物
```

---

## 常见问题

| 错误                           | 原因                                     | 解决方案                                                     |
| ------------------------------ | ---------------------------------------- | ------------------------------------------------------------ |
| `503 UNAVAILABLE`              | Gemini 服务高峰期过载                    | 设置 `GEMINI_FALLBACK_MODEL=gemini-2.5-flash`，自动重试降级  |
| `404 not found`                | 模型 ID 错误                             | 检查 `GEMINI_MODEL`，不要用 `gemini-3.1-flash-preview`       |
| `NoAudioReceived`              | 文本含特殊字符或 Edge 服务异常           | 工具会自动清理并多轮重试，全部失败时跳过该段继续             |
| `ModuleNotFoundError: jsonref` | 缺少依赖                                 | `pip install jsonref` 或 `pip install -e .`                  |
| 中文播客开头/结尾是英文        | 使用了英文默认语音或未传 `--language zh` | 加 `--language zh --role-tts-voices zh-CN-YunjianNeural ...` |
