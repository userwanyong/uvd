# SaveIt - 万能视频下载器

基于 FastAPI + yt-dlp 构建的在线视频下载服务，支持 YouTube、B站、抖音、TikTok 等 1000+ 平台。

## 特性

- **多平台支持** — 基于 yt-dlp，支持 YouTube、Bilibili、抖音、TikTok、Twitter、Instagram、小红书等 1000+ 平台
- **抖音专用解析** — 纯 HTTP API + A-Bogus 签名算法，无需浏览器，解析速度快
- **多画质选择** — 自动提取所有可用格式，从 144p 到 4K/8K 自由选择
- **实时下载进度** — 后台线程下载，前端轮询显示进度、速度、剩余大小
- **缩略图代理** — 服务端代理获取缩略图，绕过跨域和防盗链限制
- **AI 视频总结** — 自动提取字幕/文案，AI 生成智能总结、章节大纲、核心要点、交互式思维导图
- **思维导图导出** — 支持 SVG 矢量图和 PNG 高清图片两种格式下载
- **响应式界面** — 手机、平板、桌面端均可正常使用

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 下载引擎 | yt-dlp |
| 抖音解析 | HTTP API + A-Bogus 签名 (SM3) |
| AI 总结 | OpenAI 兼容 SDK (GLM / DeepSeek / OpenAI) |
| 思维导图 | markmap-view + D3.js (CDN) |
| HTTP 客户端 | httpx |
| 前端 | 原生 HTML/CSS/JS |

## 项目结构

```
uvd-glm/
├── main.py                  # FastAPI 入口
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量配置示例
├── api/
│   ├── routes.py            # 视频下载 API 路由（解析/下载/进度/缩略图代理）
│   └── ai_routes.py         # AI 总结 API 路由（启动/进度/结果）
├── core/
│   ├── downloader.py        # yt-dlp 封装，核心下载引擎
│   ├── douyin_parser.py     # 抖音视频解析器（HTTP API）
│   ├── config.py            # AI 配置加载（环境变量 / .env）
│   ├── ai_summarizer.py     # AI 总结引擎（调用 OpenAI 兼容 API）
│   ├── subtitle_extractor.py # 字幕/文案提取器
│   └── douyin/
│       └── abogus.py        # A-Bogus 签名算法（纯 Python）
└── static/
    ├── index.html           # 前端页面
    ├── css/
    │   ├── style.css        # 主样式
    │   └── ai-summary.css   # AI 总结功能样式
    └── js/
        ├── app.js           # 前端主逻辑
        └── ai-summary.js    # AI 总结前端逻辑 + 思维导图渲染
```

## 快速开始

### 环境要求

- Python 3.10+

### 安装

```bash
pip install -r requirements.txt
```

### AI 功能配置（可选）

如需使用 AI 视频总结功能，在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
# 选择 AI 后端: glm / deepseek / openai
AI_PROVIDER=glm

# GLM (智谱)
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AI_API_KEY=your_api_key_here
AI_MODEL=glm-4.7-flash
```

支持任何 OpenAI 兼容接口，包括智谱 GLM、DeepSeek、OpenAI 等，详见 `.env.example` 中的配置示例。

> 不配置 AI 则不影响视频下载功能，AI 按钮仍可点击但会提示配置缺失。

### 启动

```bash
python main.py
```

服务启动后访问 http://127.0.0.1:8000

## API 接口

### 视频下载

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/info` | 解析视频 URL，返回视频信息和可用格式 |
| POST | `/api/download` | 开始下载，返回 task_id |
| GET | `/api/progress/{task_id}` | 查询下载进度 |
| GET | `/api/file/{task_id}` | 下载完成的文件 |
| GET | `/api/proxy-thumbnail/{encoded_url}` | 代理获取缩略图 |

### AI 视频总结

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai/summarize` | 启动 AI 总结任务，返回 task_id |
| GET | `/api/ai/progress/{task_id}` | 查询总结进度 |
| GET | `/api/ai/result/{task_id}` | 获取完整总结结果 |

### 解析视频

```bash
curl -X POST http://127.0.0.1:8000/api/info \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## AI 视频总结

解析视频后，点击「AI 总结」按钮即可自动生成结构化内容：

1. **智能总结** — 3-5 句话概括视频核心内容
2. **章节大纲** — 按逻辑顺序梳理主要章节和要点
3. **核心要点** — 提取 5-8 个关键知识点或观点
4. **思维导图** — 基于 markmap 渲染的交互式思维导图，支持滚轮缩放和拖拽平移

### 思维导图

- 采用 markmap-view 渲染引擎，曲线连接、分支彩色编码
- 暗色主题配色，与应用整体风格统一
- 支持导出为 **SVG 矢量图**（无限放大不失真）或 **PNG 高清图片**（2x 分辨率）
- CDN 不可用时自动降级为简单树形展示

### 工作流程

```
视频 URL → 提取字幕/文案 → AI 模型生成结构化内容 → 前端分 Tab 展示
```

- 文本来源优先使用视频字幕，无字幕时使用视频文案
- 文本超长时自动截断（12,000 字），避免超出模型上下文限制
- 后台线程异步处理，前端轮询进度，不阻塞下载功能

## 抖音解析说明

抖音视频使用专用解析路径，基于纯 HTTP 请求实现：

1. **短链接解析** — 自动跟随 `v.douyin.com` 重定向，提取 aweme_id
2. **A-Bogus 签名** — 纯 Python 实现抖音反爬签名算法（基于 SM3 国密哈希 + RC4 加密）
3. **ttwid 获取** — 自动获取并缓存 ttwid cookie（24 小时有效期）
4. **多清晰度** — 支持 360p 到 4K 多种画质

签名算法参考 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)（Apache 2.0），原始作者 [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)。

## License

MIT
