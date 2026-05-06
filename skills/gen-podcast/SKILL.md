---
name: gen-podcast
description: >-
  AI 播客生成技能：从网页/YouTube/PDF 自动提取内容，通过 Gemini LLM 生成多角色对话脚本，
  Edge TTS 合成语音，输出 MP3 + 逐字高亮字幕（JSON / WebVTT 卡拉OK / 增强 LRC / SRT，由 Gemini 音频理解生成）。
  可选上传 Cloudflare R2 并写入 D1 数据库。
  已发布到 PyPI（pip install gen-podcast）。
  当用户需要生成播客、将文章/视频/论文转为播客音频、制作 AI 播客、文本转语音对话、
  为音频生成逐字高亮字幕时使用此技能。
  触发关键词：播客生成、podcast、文章转播客、视频转播客、论文转播客、AI播客、TTS对话、
  逐字字幕、卡拉OK字幕、word-level subtitles、karaoke subtitles、
  generate podcast、content to podcast、text to speech dialogue、gen-podcast、subtitle-gen。
---

# AI 播客生成 (gen-podcast)

将任意来源内容（网页文章、YouTube 视频、PDF 文档）自动转换为多角色对话播客音频，并可选生成**逐字高亮字幕**（用于视频字幕逐字渲染或播客文字同步高亮）。

- PyPI: https://pypi.org/project/gen-podcast/
- 在线体验: https://podcast-997.pages.dev/

## 前置条件

### 安装

```bash
pip install gen-podcast
```

要求 Python >= 3.10（推荐 3.11+）。

### 环境变量

复制 `.env.example` 为 `.env`，至少配置：

| 变量 | 必需 | 说明 |
|------|------|------|
| `GOOGLE_API_KEY` | 是 | Google Gemini API 密钥 |
| `GEMINI_MODEL` | 否 | 默认 `gemini-3-flash-preview` |
| `GEMINI_FALLBACK_MODEL` | 否 | 503 时降级模型，如 `gemini-2.5-flash` |
| `GEMINI_MAX_RETRIES` | 否 | LLM 重试次数，默认 `6` |
| `GEMINI_RETRY_BASE_SEC` | 否 | 重试基础等待秒数（指数退避），默认 `2` |
| `GEMINI_SUBTITLE_MODEL` | 否 | 逐字字幕用的音频模型，默认 `gemini-2.5-flash` |
| `SUBTITLE_CHUNK_SEC` | 否 | 长音频切片秒数，默认 `180`（撞 `MAX_TOKENS` 会自适应对半切到 30s 为止） |
| `ROUND_CN` | 否 | 播客对话轮数（默认随机 20–50） |

仅在需要上传/入库时配置：

| 变量 | 说明 |
|------|------|
| `PODCAST_D1_DB_ID` | Cloudflare D1 数据库 ID |
| `CLOUDFLARE_API_KEY` | Cloudflare API Token |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账号 ID |
| `CLOUDFLARE_ACCESS_KEY` / `CLOUDFLARE_SECRET_KEY` | R2 存储密钥 |
| `S3_BUCKET_URL` | R2 公开 URL |
| `SILICONCLOUD_API_KEY` | SiliconFlow 封面生成 |

## 工作流程

```
来源（URL / PDF）
      │
      ▼
ContentExtractor         ← 网页 / YouTube / PDF 文本提取
      │
      ▼
Gemini LLM (instructor)  ← 流式生成多角色播客对话（结构化输出）
      │
      ▼
Edge TTS (逐角色合成)     ← 自动清理特殊字符，指数退避重试
      │
      ▼
pydub 合并 MP3 + WebVTT（句子级）
      │（可选）
      ├── SiliconFlow 生成封面
      ├── Gemini 音频理解 → 逐字字幕（json / vtt / lrc / srt，长音频自动分段；需 --subtitles 显式启用）
      ▼
Cloudflare R2 上传（音频 + 封面 + 字幕） + D1 写入元数据
      │（可选）
      ▼
gen_podcasts_xml     ← 从 D1 查询已发布播客 → 生成 RSS XML → 上传 R2
```

## 使用方式

### 方式一：端到端生成并入库（推荐）

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

# 需要逐字字幕时显式加 --subtitles（字幕默认关闭；启用前需先对 D1 做 subtitle_* 列迁移）
gen-podcast run --subtitles --language zh \
    "https://en.wikipedia.org/wiki/Large_language_model"
```

### 方式二：仅生成音频（不入库）

```bash
content-parser-tts instruct-content-tts \
    "https://en.wikipedia.org/wiki/Large_language_model"

# 中文
content-parser-tts instruct-content-tts \
    --role-tts-voices zh-CN-YunjianNeural \
    --role-tts-voices zh-CN-XiaoxiaoNeural \
    --language zh \
    "https://en.wikipedia.org/wiki/Large_language_model"
```

### 方式三：合并已有分段音频

```bash
content-parser-tts merge-audio-files \
    audios/podcast/Large_language_model/0  audios/podcast/LLM.mp3
```

### 方式四：为任意音频生成逐字字幕（独立使用）

```bash
# 中文（按 2-5 字短语切 token）
subtitle-gen generate audios/podcast/LLM.mp3 --language zh

# 英文（按词切 token）
subtitle-gen generate audios/podcast/LLM.mp3 --language en

# 同时提供对话稿辅助对齐
subtitle-gen generate audios/podcast/LLM.mp3 \
    --language zh \
    --script-file audios/podcast/LLM.txt \
    --output-dir /tmp/subs

# 只生成特定格式
subtitle-gen generate audios/podcast/LLM.mp3 --formats json --formats vtt

# 自定义切片长度（长音频）
subtitle-gen generate audios/podcast/LLM.mp3 --language zh --chunk-sec 180
```

同目录输出 4 份文件：`{stem}.words.json` / `{stem}.words.vtt`（WebVTT 内联 `<00:00:00.500>` 卡拉OK 标签）/ `{stem}.words.lrc`（A2 增强 LRC）/ `{stem}.srt`。

### 方式五：生成 RSS 订阅源

```bash
# 从 D1 播客数据生成 rss.xml（Apple Podcasts 兼容格式）
gen-podcasts-xml gen_xml_from_d1_podcast

# 生成并上传到 Cloudflare R2
gen-podcasts-xml gen_xml_from_d1_podcast --is-upload
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `SOURCES` | — | 一个或多个来源（网页 URL / YouTube URL / PDF 路径） |
| `--role-tts-voices` | `en-US-JennyNeural` `en-US-EricNeural` | Edge TTS 语音，可重复指定 |
| `--language` | `en` | 对话语言：`zh` / `en` / `ja` / `ko` 等 |
| `--save-dir` | `./audios/podcast` | 音频输出目录 |
| `--category` | `0` | 分类 ID（0=未知 1=科技 2=教育 3=美食 4=旅行 5=代码 …） |
| `--is-published` | `False` | 仅 `run` 可用，标记为已发布并打印访问链接 |
| `--subtitles` / `--no-subtitles` | `False` | 加 `--subtitles` 启用 Gemini 逐字字幕并上传 R2、URL 写入 D1（默认关闭） |
| `--subtitle-model` | `""` | 仅字幕阶段覆盖 `GEMINI_SUBTITLE_MODEL` |

## 推荐 TTS 语音

### 中文

| 语音 ID | 性别 | 风格 |
|---------|------|------|
| `zh-CN-YunjianNeural` | 男 | 播音风格 |
| `zh-CN-YunxiNeural` | 男 | 叙述风格 |
| `zh-CN-YunyangNeural` | 男 | 新闻风格 |
| `zh-CN-XiaoxiaoNeural` | 女 | 自然亲切（推荐） |
| `zh-CN-XiaoyiNeural` | 女 | 温柔甜美 |

### 英文

| 语音 ID | 性别 |
|---------|------|
| `en-US-EricNeural` | 男 |
| `en-US-JennyNeural` | 女 |

> `--language zh` 时若未指定中文语音，工具会自动替换并打印推荐列表。

## 输入/输出

**支持的输入类型**：
- HTTP(S) URL（含 `youtube.com` / `youtu.be` → 自动识别为 YouTube 字幕提取）
- HTTP(S) URL（其他 → 网页正文提取）
- 本地 `.pdf` 文件路径 → PDF 全文提取

**输出产物**：
- 分段音频：`{save_dir}/{title}/{index}/{i}_{role_name}.mp3`
- 分段字幕：`{save_dir}/{title}/{index}/{i}_{role_name}.vtt`（Edge TTS 输出，句子级）
- 合并音频：`{save_dir}/{title}_{timestamp}.mp3`
- 逐字字幕（默认**关闭**，加 `--subtitles` 启用）：与合并音频同目录同前缀
  - `{title}_{timestamp}.words.json` — 每个 token 的 `start`/`end`，前端渲染首选
  - `{title}_{timestamp}.words.vtt` — WebVTT 内联 `<00:00:00.500>` 卡拉OK 标签
  - `{title}_{timestamp}.words.lrc` — A2 增强 LRC（逐词时间戳）
  - `{title}_{timestamp}.srt` — 句子级 SRT

## 常见问题排查

| 错误 | 原因 | 解决 |
|------|------|------|
| `503 UNAVAILABLE` | Gemini 过载 | 设置 `GEMINI_FALLBACK_MODEL=gemini-2.5-flash` |
| `404 not found` | 模型 ID 错误 | 检查 `GEMINI_MODEL`，不存在 `gemini-3.1-flash-preview` |
| `NoAudioReceived` | 文本含特殊字符 | 工具自动清理重试，全部失败跳过该段 |
| 中文播客出现英文 | 未指定中文语音 | 加 `--language zh --role-tts-voices zh-CN-...` |
| `ModuleNotFoundError: jsonref` | 缺少依赖 | `pip install gen-podcast` |
| `Gemini returned non-JSON subtitle payload` / `MAX_TOKENS` | 字幕输出被截断（单次音频过长） | v0.1.3+ 会自动对半重试，若仍持续报错可显式 `--chunk-sec 120` 或 60 |
| 最后一条对话丢失 | v0.1.2 流式末尾 bug | 升级到 v0.1.3+（已修复） |
| D1 插入失败 `no such column: subtitle_json_url` | 旧库未迁移 | 对已有 D1 跑 4 条 `ALTER TABLE podcast ADD COLUMN subtitle_*_url text DEFAULT "";` |

## 辅助命令

| 命令 | 说明 |
|------|------|
| `content-extractor extract-content <URL>` | 仅提取内容预览 |
| `gen-podcast get-source-type <URL>` | 判断来源类型 |
| `insert-podcast insert-podcast-to-d1 ...` | 手动入库 |
| `insert-podcast update-podcast-subtitles-to-d1 <pid> --subtitle-json-url ...` | 为已存在播客回填字幕 R2 URL |
| `subtitle-gen generate <audio> --language <code>` | 为任意音频生成逐字字幕（4 种格式） |
| `siliconflow-api gen-image <prompt>` | 手动生成封面 |
| `gen-podcasts-xml gen_xml_from_d1_podcast` | 从 D1 生成 RSS XML |
| `gen-podcasts-xml gen_xml_from_d1_podcast --is-upload` | 生成 RSS XML 并上传至 R2 |

## 在 Agent 中使用

Agent 执行此技能时，遵循以下步骤：

1. **确认环境**：确保 `gen-podcast` 已安装（`pip install gen-podcast`）且 `.env` 已配置 `GOOGLE_API_KEY`
2. **确定来源**：从用户请求中提取 URL 或 PDF 路径
3. **选择语言和语音**：根据用户需求选择 `--language` 和 `--role-tts-voices`
4. **执行生成**：
   - 仅需音频 → `content-parser-tts instruct-content-tts`
   - 仅需为已有音频做逐字字幕 → `subtitle-gen generate <audio> --language <code>`
   - 需要入库发布（含自动字幕）→ `gen-podcast run --subtitles`（字幕默认关闭，需显式启用；启用前请先确认 D1 已迁移 4 个 `subtitle_*_url` 列）；不需字幕时直接 `gen-podcast run`
5. **返回结果**：告知用户生成的音频/字幕文件路径，或在线播客链接（若已发布到 https://podcast-997.pages.dev/）

详细模块 API 参考见 [reference.md](reference.md)。
