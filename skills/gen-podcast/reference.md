# gen-podcast 详细参考

## 包信息

- **PyPI 包名**：`gen-podcast`
- **安装命令**：`pip install gen-podcast`
- **CLI 入口**：`gen-podcast`

## CLI 命令

### gen-podcast — 端到端入口

| 子命令 | 说明 |
|--------|------|
| `gen-podcast run [SOURCES...]` | 端到端：提取内容 → LLM 生成对话 → TTS → 上传 R2 → 写入 D1 |
| `gen-podcast get-source-type <url>` | 返回来源类型：`youtube` / `website` / 文件扩展名 |

## 内容提取器

| 提取器 | 来源类型 |
|--------|----------|
| 网页提取 | HTTP(S) 网页（BeautifulSoup） |
| YouTube 字幕 | YouTube 视频字幕 |
| PDF 提取 | 本地 PDF 文件（PyMuPDF） |

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
| `gemini-2.5-flash` | 稳定版，适合生产 |
| `gemini-2.5-pro` | 最强推理，成本较高 |

> `gemini-3.1-flash-preview` 不存在，会返回 404。

## 重要约束

- TTS 语音数量必须与 LLM 输出的角色数量一致（默认 2 角色 2 语音）
- `--language zh` 时若使用英文语音，工具自动替换并提示
- 默认作者名为 `weedge`
- 对话轮数默认随机 20–50 轮（可通过 `ROUND_CN` 环境变量控制）
- Gemini 主模型 503 时自动降级到 `GEMINI_FALLBACK_MODEL`
