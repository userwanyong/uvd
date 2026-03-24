# SaveIt - 万能视频下载器

基于 FastAPI + yt-dlp 构建的在线视频下载服务，支持 YouTube、B站、抖音、TikTok 等 1000+ 平台。

## 特性

- **多平台支持** — 基于 yt-dlp，支持 YouTube、Bilibili、抖音、TikTok、Twitter、Instagram、小红书等 1000+ 平台
- **抖音专用解析** — 纯 HTTP API + A-Bogus 签名算法，无需浏览器，解析速度快
- **多画质选择** — 自动提取所有可用格式，从 144p 到 4K/8K 自由选择
- **实时下载进度** — 后台线程下载，前端轮询显示进度、速度、剩余大小
- **缩略图代理** — 服务端代理获取缩略图，绕过跨域和防盗链限制
- **响应式界面** — 手机、平板、桌面端均可正常使用

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 下载引擎 | yt-dlp |
| 抖音解析 | HTTP API + A-Bogus 签名 (SM3) |
| HTTP 客户端 | httpx |
| 前端 | 原生 HTML/CSS/JS |

## 项目结构

```
uvd/
├── main.py                  # FastAPI 入口
├── requirements.txt         # Python 依赖
├── api/
│   └── routes.py            # API 路由（解析/下载/进度/缩略图代理）
├── core/
│   ├── downloader.py        # yt-dlp 封装，核心下载引擎
│   ├── douyin_parser.py     # 抖音视频解析器（HTTP API）
│   └── douyin/
│       └── abogus.py        # A-Bogus 签名算法（纯 Python）
└── static/
    ├── index.html           # 前端页面
    ├── css/style.css        # 样式
    └── js/app.js            # 前端逻辑
```

## 快速开始

### 环境要求

- Python 3.10+

### 安装

```bash
pip install -r requirements.txt
```

### 启动

```bash
python main.py
```

服务启动后访问 http://127.0.0.1:8000

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/info` | 解析视频 URL，返回视频信息和可用格式 |
| POST | `/api/download` | 开始下载，返回 task_id |
| GET | `/api/progress/{task_id}` | 查询下载进度 |
| GET | `/api/file/{task_id}` | 下载完成的文件 |
| GET | `/api/proxy-thumbnail/{encoded_url}` | 代理获取缩略图 |

### 解析视频

```bash
curl -X POST http://127.0.0.1:8000/api/info \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## 抖音解析说明

抖音视频使用专用解析路径，基于纯 HTTP 请求实现：

1. **短链接解析** — 自动跟随 `v.douyin.com` 重定向，提取 aweme_id
2. **A-Bogus 签名** — 纯 Python 实现抖音反爬签名算法（基于 SM3 国密哈希 + RC4 加密）
3. **ttwid 获取** — 自动获取并缓存 ttwid cookie（24 小时有效期）
4. **多清晰度** — 支持 360p 到 4K 多种画质

签名算法参考 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)（Apache 2.0），原始作者 [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)。

## License

MIT
