# gen-podcast 详细参考

## 包信息

- **PyPI 包名**：`gen-podcast`
- **安装命令**：`pip install gen-podcast`
- **CLI 入口**：`gen-podcast`

## CLI 命令

### gen-podcast — 端到端入口

| 子命令 | 说明 |
|--------|------|
| `gen-podcast run [SOURCES...]` | 端到端：提取内容 → LLM 生成对话 → TTS → 上传 R2 → 写入 D1（字幕**默认关闭**） |
| `gen-podcast run --subtitles [SOURCES...]` | 同上并生成逐字字幕（上传 R2 + 写入 D1 的 4 个 subtitle_*_url 列，需先做迁移） |
| `gen-podcast get-source-type <url>` | 返回来源类型：`youtube` / `website` / 文件扩展名 |

### subtitle-gen — 逐字字幕

| 子命令 | 说明 |
|--------|------|
| `subtitle-gen generate <audio> --language <code>` | 上传音频到 Gemini，输出 4 种字幕文件 |

常用选项：

| 选项 | 说明 |
|------|------|
| `--language` | 语言代码（`zh` / `en` / `ja` / `ko` …）；影响切 token 策略 |
| `--script-file <path>` | 可选对话稿，辅助 Gemini 对齐 token |
| `--output-dir <dir>` | 输出目录，默认与音频同目录 |
| `--formats json --formats vtt ...` | 只生成指定格式（默认全部 4 种） |
| `--model <id>` | 覆盖 `GEMINI_SUBTITLE_MODEL` |
| `--chunk-sec <n>` | 长音频切片秒数，覆盖 `SUBTITLE_CHUNK_SEC` |

字幕文件命名：`{audio_stem}.words.json` / `.words.vtt` / `.words.lrc` / `.srt`。

### insert-podcast — R2 + D1

| 子命令 | 说明 |
|--------|------|
| `insert-podcast insert-podcast-to-d1 <audio> <title> <author> <speakers> ...` | 上传音频 + 生成封面 + 写入 D1（可选携带 4 个 `--subtitle-*-url`） |
| `insert-podcast update-podcast-cover-to-d1 <pid> <url>` | 为已存在播客更新封面 |
| `insert-podcast update-podcast-subtitles-to-d1 <pid> --subtitle-json-url ... --subtitle-vtt-url ...` | 回填字幕 URL |

## 内容提取器

| 提取器 | 来源类型 |
|--------|----------|
| 网页提取 | HTTP(S) 网页（BeautifulSoup） |
| YouTube 字幕 | YouTube 视频字幕 |
| PDF 提取 | 本地 PDF 文件或 arXiv PDF URL（PyMuPDF） |

来源类型自动识别：URL 含 `youtube.com` / `youtu.be` → YouTube，其他 URL → 网页，`.pdf` 后缀 → PDF。

## 支持的语言代码

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

## 支持的 Gemini 模型

| 模型 ID | 说明 |
|---------|------|
| `gemini-3-flash-preview` | 默认，Gemini 3 Flash（速度快） |
| `gemini-3.1-flash-lite-preview` | Gemini 3.1 轻量版 |
| `gemini-2.5-flash` | 稳定版，适合生产；**字幕默认** |
| `gemini-2.5-pro` | 最强推理，成本较高 |

> `gemini-3.1-flash-preview` 不存在，会返回 404。字幕生成用独立的 `GEMINI_SUBTITLE_MODEL`（需支持音频输入）。

## 字幕输出格式（v0.1.3+）

| 文件后缀 | 格式 | 典型用途 |
|---------|------|---------|
| `.words.json` | 结构化 JSON（segments[{speaker,text,start,end,words:[{text,start,end}]}]） | 前端/视频播放器逐词高亮渲染 |
| `.words.vtt` | WebVTT，cue 内联 `<00:00:00.500>` 时间标签 | 浏览器 `<track>` 元素，卡拉OK 字幕 |
| `.words.lrc` | 增强 LRC（A2 扩展），`[mm:ss.xx]<mm:ss.xx>word` | 音乐/播客播放器逐词高亮 |
| `.srt` | 标准 SRT，句子级 | 视频播放器通用字幕 |

Token 切分策略：
- CJK 语言（`zh` / `ja` / `ko`）：每个 `word` 是 2–5 字自然短语，避免单字闪烁
- 空格分词语言（`en` / `es` / `fr` …）：每个 `word` 是一个词

## D1 表 schema（`podcast`）

| 列 | 类型 | 说明 |
|----|------|------|
| `pid` | text | 唯一 ID |
| `title` / `description` / `author` / `speakers` / `source` | text | 基本元数据 |
| `audio_url` / `cover_img_url` | text | R2 公开 URL |
| `audio_content` | text | 完整对话文字稿 |
| `duration` / `audio_size` | int | 秒 / 字节 |
| `category` / `status` / `is_published` | int / bool | 分类与发布状态 |
| `create_time` / `update_time` | text | 时间戳 |
| `subtitle_json_url` / `subtitle_vtt_url` / `subtitle_lrc_url` / `subtitle_srt_url` | text | 逐字字幕 R2 URL（**v0.1.3 新增**） |

已有库迁移：

```sql
ALTER TABLE podcast ADD COLUMN subtitle_json_url text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_vtt_url  text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_lrc_url  text DEFAULT "";
ALTER TABLE podcast ADD COLUMN subtitle_srt_url  text DEFAULT "";
```

完整 schema 在 `podcast/sql/podcast.sql`。

## 重要约束

- TTS 语音数量必须与 LLM 输出的角色数量一致（默认 2 角色 2 语音）
- `--language zh` 时若使用英文语音，工具自动替换并提示
- 默认作者名为 `weedge`
- 对话轮数默认随机 20–50 轮（可通过 `ROUND_CN` 环境变量控制）
- Gemini 主模型 503 时自动降级到 `GEMINI_FALLBACK_MODEL`
- 字幕生成会对长音频自动按 `SUBTITLE_CHUNK_SEC`（默认 300 秒）切片，每段独立调用 Gemini 并按偏移量合并；若仍撞 `MAX_TOKENS`，进一步降低该值（如 180）
- `gen-podcast run` **默认关闭**字幕（`--no-subtitles` 等同默认行为）；需要时显式传 `--subtitles`，并确保 D1 已迁移 4 个 `subtitle_*_url` 列，否则 `insert_podcast_to_d1` 会报 `no such column`
