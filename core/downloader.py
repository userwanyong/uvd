"""
yt-dlp 封装层 —— 核心下载引擎
直接使用 yt-dlp 作为 Python 库，不修改源码。
抖音使用专用 HTTP API 解析器（A-Bogus 签名）。
"""

import os
import re
import time
import uuid
import threading
from dataclasses import dataclass, field

import yt_dlp


@dataclass
class FormatInfo:
    format_id: str
    resolution: str
    ext: str
    filesize: int | None
    filesize_approx: int | None
    fps: float | None
    vcodec: str
    acodec: str
    tbr: float | None
    label: str  # 给用户看的友好描述


@dataclass
class VideoInfo:
    title: str
    thumbnail: str
    duration: float
    duration_string: str
    uploader: str
    upload_date: str
    description: str
    formats: list[FormatInfo]
    best_format_id: str | None = None


@dataclass
class DownloadProgress:
    task_id: str
    status: str = "pending"  # pending / downloading / completed / error
    progress: float = 0.0
    speed: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    filename: str = ""
    error: str = ""


# 内存中保存下载任务状态
_tasks: dict[str, DownloadProgress] = {}


def _human_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "未知"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_format_label(fmt) -> str:
    """生成给用户看的格式描述"""
    parts = []
    if fmt.get("vcodec") and fmt["vcodec"] != "none":
        parts.append(fmt.get("resolution") or "?")
        if fmt.get("fps"):
            parts.append(f"{fmt['fps']}fps")
        parts.append(fmt.get("vcodec") or "?")
    if fmt.get("acodec") and fmt["acodec"] != "none":
        if parts:
            parts.append("+")
        parts.append(fmt.get("acodec") or "?")
    label = " ".join(parts) if parts else "仅音频"
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        label += f" ({_human_size(size)})"
    return label


def _parse_formats(raw_formats: list[dict]) -> list[FormatInfo]:
    """从 yt-dlp 返回的格式列表中提取关键信息"""
    formats = []
    for f in raw_formats:
        # 跳过不包含视频或音频的纯清单条目
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        if vcodec == "none" and acodec == "none":
            continue

        fmt = FormatInfo(
            format_id=f["format_id"],
            resolution=f.get("resolution", ""),
            ext=f.get("ext", ""),
            filesize=f.get("filesize"),
            filesize_approx=f.get("filesize_approx"),
            fps=f.get("fps"),
            vcodec=vcodec,
            acodec=acodec,
            tbr=f.get("tbr"),
            label=_build_format_label(f),
        )
        formats.append(fmt)
    return formats


def _normalize_url(url: str) -> str:
    """URL 预处理：将平台特殊 URL 转换为 yt-dlp 支持的标准格式"""
    # 抖音精选页 URL -> 标准 video URL
    # https://www.douyin.com/jingxuan?modal_id=7615047783732677809
    #   -> https://www.douyin.com/video/7615047783732677809
    m = re.match(r'https?://(?:www\.)?douyin\.com/\w+\?modal_id=(\d+)', url)
    if m:
        url = f'https://www.douyin.com/video/{m.group(1)}'
    # 抖音笔记页 URL
    m = re.match(r'https?://(?:www\.)?douyin\.com/note/(\d+)', url)
    if m:
        url = f'https://www.douyin.com/video/{m.group(1)}'
    return url


def _is_douyin_url(url: str) -> bool:
    return bool(re.match(r'https?://(?:www\.)?douyin\.com/', url))


def extract_info(url: str) -> VideoInfo:
    """
    解析视频URL，获取视频信息和可用格式列表。
    不实际下载视频。
    抖音使用专用 HTTP API 解析器，其他平台使用 yt-dlp。
    """
    url = _normalize_url(url)

    if _is_douyin_url(url):
        return _extract_douyin_info(url)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 2,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        info = ydl.sanitize_info(info)

    raw_formats = info.get("formats", [])
    formats = _parse_formats(raw_formats)

    # 找最佳格式（yt-dlp 自动选择的）
    best_format_id = None
    if info.get("format_id"):
        best_format_id = info["format_id"]
    elif formats:
        # 按 tbr 降序，优先选有视频的
        video_fmts = [f for f in formats if f.vcodec != "none"]
        if video_fmts:
            best_format_id = max(video_fmts, key=lambda f: f.tbr or 0).format_id
        else:
            best_format_id = max(formats, key=lambda f: f.tbr or 0).format_id

    return VideoInfo(
        title=info.get("title", "未知标题"),
        thumbnail=info.get("thumbnail", ""),
        duration=info.get("duration", 0) or 0,
        duration_string=_human_duration(info.get("duration")),
        uploader=info.get("uploader", ""),
        upload_date=info.get("upload_date", ""),
        description=(info.get("description") or "")[:500],
        formats=formats,
        best_format_id=best_format_id,
    )


def _extract_douyin_info(url: str) -> VideoInfo:
    """使用 HTTP API 解析抖音视频"""
    from core.douyin_parser import (
        parse as douyin_parse,
    )

    result = douyin_parse(url)

    formats = []
    for f in result["formats"]:
        fmt = FormatInfo(
            format_id=f["format_id"],
            resolution=f.get("resolution", ""),
            ext="mp4",
            filesize=f.get("filesize") or None,
            filesize_approx=None,
            fps=None,
            vcodec="h264",
            acodec="aac",
            tbr=None,
            label=f["label"],
        )
        formats.append(fmt)

    return VideoInfo(
        title=result["title"],
        thumbnail=result["thumbnail"],
        duration=result["duration"],
        duration_string=result["duration_string"],
        uploader=result["uploader"],
        upload_date=result["upload_date"],
        description=result["description"],
        formats=formats,
        best_format_id=result.get("best_format_id"),
    )


def _download_hook(progress: DownloadProgress, d: dict):
    """yt-dlp 下载进度回调"""
    if d["status"] == "downloading":
        progress.status = "downloading"
        progress.downloaded_bytes = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        progress.total_bytes = total
        progress.speed = d.get("speed", 0)
        if total > 0:
            progress.progress = min(progress.downloaded_bytes / total * 100, 100)
    elif d["status"] == "finished":
        progress.status = "completed"
        progress.progress = 100
        progress.filename = d.get("filename", "")


def download_video(
    url: str,
    format_id: str | None = None,
    output_dir: str = "downloads",
) -> str:
    """
    下载视频，返回 task_id 用于查询进度。
    实际下载在后台线程中执行。
    """
    url = _normalize_url(url)

    if _is_douyin_url(url):
        return _download_douyin(url, format_id, output_dir)

    task_id = str(uuid.uuid4())[:8]
    progress = DownloadProgress(task_id=task_id, status="pending")
    _tasks[task_id] = progress

    os.makedirs(output_dir, exist_ok=True)

    def _do_download():
        ydl_opts = {
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [lambda d: _download_hook(progress, d)],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 2,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        if format_id:
            ydl_opts["format"] = format_id
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            progress.status = "completed"
        except Exception as e:
            progress.status = "error"
            progress.error = str(e)

    t = threading.Thread(target=_do_download, daemon=True)
    t.start()

    return task_id


def _download_douyin(
    url: str,
    format_id: str | None,
    output_dir: str,
) -> str:
    """使用 httpx 下载抖音视频（从 API 缓存中获取直链）"""
    import httpx
    from core.douyin_parser import (
        parse as douyin_parse,
        extract_video_id,
        get_cached,
        sanitize_filename,
    )

    video_id = extract_video_id(url)
    cached = get_cached(video_id) if video_id else None
    if not cached:
        cached = douyin_parse(url)

    # 找下载 URL
    download_url = cached.get("default_download_url", "")
    if format_id:
        for f in cached.get("formats", []):
            if f["format_id"] == format_id:
                download_url = f["url"]
                break
    if not download_url:
        raise ValueError("无法获取视频下载地址")

    task_id = str(uuid.uuid4())[:8]
    progress = DownloadProgress(task_id=task_id, status="pending")
    _tasks[task_id] = progress

    os.makedirs(output_dir, exist_ok=True)
    filename = sanitize_filename(cached["title"][:80]) + ".mp4"
    filepath = os.path.join(output_dir, filename)

    def _do_download():
        import time as _time
        try:
            last_time = _time.time()
            last_bytes = 0
            with httpx.stream(
                "GET", download_url,
                follow_redirects=True,
                timeout=120,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.douyin.com/",
                },
            ) as resp:
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = _time.time()
                        elapsed = now - last_time
                        if elapsed >= 0.5:
                            progress.speed = (downloaded - last_bytes) / elapsed
                            progress.downloaded_bytes = downloaded
                            progress.total_bytes = total
                            progress.status = "downloading"
                            if total > 0:
                                progress.progress = min(downloaded / total * 100, 100)
                            last_time = now
                            last_bytes = downloaded
            progress.status = "completed"
            progress.progress = 100
            progress.filename = filepath
        except Exception as e:
            progress.status = "error"
            progress.error = str(e)

    t = threading.Thread(target=_do_download, daemon=True)
    t.start()

    return task_id


def get_progress(task_id: str) -> DownloadProgress | None:
    """查询下载进度"""
    return _tasks.get(task_id)


def get_download_file(task_id: str) -> str | None:
    """获取下载完成的文件路径"""
    progress = _tasks.get(task_id)
    if progress and progress.status == "completed" and progress.filename:
        return progress.filename
    return None
