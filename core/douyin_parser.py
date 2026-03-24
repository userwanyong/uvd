"""
抖音视频解析器 —— 基于 HTTP 请求 + A-Bogus 签名
直接调用抖音内部 API，无需浏览器。
签名算法来源: Evil0ctal/Douyin_TikTok_Download_API (Apache 2.0)
"""

import re
import time
import httpx
from urllib.parse import urlencode, quote

from core.douyin.abogus import ABogus

# 缓存已解析的视频信息 (video_id -> info dict)
_cache: dict[str, dict] = {}

# 缓存 ttwid
_ttwid_cache: str = ""
_ttwid_expire: float = 0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
)

# 抖音 API 端点
API_DETAIL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
TTWID_DATA = (
    '{"region":"cn","aid":1768,"needFid":false,"service":"www.ixigua.com",'
    '"migrate_info":{"ticket":"","source":"node"},"cbUrlProtocol":"https","union":true}'
)

# API 请求的公共参数
_COMMON_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "130.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "130.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": "12",
    "device_memory": "8",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "0",
}


def is_douyin_url(url: str) -> bool:
    return bool(re.match(r'https?://(?:[\w.-]*\.)?(douyin|iesdouyin)\.com/', url))


def extract_video_id(url: str) -> str | None:
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'modal_id=(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/note/(\d+)', url)
    if m:
        return m.group(1)
    return None


def normalize_url(url: str) -> str:
    """URL 预处理：将平台特殊 URL 转换为标准 video URL"""
    m = re.match(r'https?://(?:www\.)?douyin\.com/\w+\?modal_id=(\d+)', url)
    if m:
        url = f'https://www.douyin.com/video/{m.group(1)}'
    m = re.match(r'https?://(?:www\.)?douyin\.com/note/(\d+)', url)
    if m:
        url = f'https://www.douyin.com/video/{m.group(1)}'
    return url


def _resolve_aweme_id(url: str) -> str:
    """
    从 URL 中提取 aweme_id，短链接通过 HTTP 重定向解析。
    支持格式:
      - https://www.douyin.com/video/123456789
      - https://www.douyin.com/note/123456789
      - https://v.douyin.com/xxxxx/ (短链接)
      - https://www.iesdouyin.com/share/video/123456789/...
    """
    # 先尝试直接匹配
    video_id = extract_video_id(url)
    if video_id:
        return video_id

    # 短链接需要跟随重定向
    with httpx.Client(follow_redirects=True, timeout=15) as client:
        resp = client.get(url, headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://www.douyin.com/",
        })
        final_url = str(resp.url)

    video_id = extract_video_id(final_url)
    if not video_id:
        raise ValueError(f"无法从 URL 中提取视频 ID: {final_url}")
    return video_id


def _get_ttwid() -> str:
    """获取或刷新 ttwid（有效期较长，缓存复用）"""
    global _ttwid_cache, _ttwid_expire

    now = time.time()
    if _ttwid_cache and now < _ttwid_expire:
        return _ttwid_cache

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            TTWID_URL,
            content=TTWID_DATA,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        ttwid = httpx.Cookies(resp.cookies).get("ttwid", "")
        if not ttwid:
            raise ValueError("无法获取 ttwid")

    _ttwid_cache = ttwid
    # ttwid 有效期较长，缓存 24 小时
    _ttwid_expire = now + 86400
    return ttwid


def parse(url: str) -> dict:
    """解析抖音视频，返回视频信息 dict。基于纯 HTTP 请求，无需浏览器。"""
    url = normalize_url(url)
    aweme_id = _resolve_aweme_id(url)

    if aweme_id in _cache:
        return _cache[aweme_id]

    ttwid = _get_ttwid()

    # 构建请求参数
    params = {**_COMMON_PARAMS, "aweme_id": aweme_id, "msToken": ""}

    # 生成 A-Bogus 签名
    ab = ABogus()
    a_bogus = ab.get_value(params)
    params["a_bogus"] = a_bogus

    # 请求抖音 API
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            API_DETAIL,
            params=params,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.douyin.com/",
                "Cookie": f"ttwid={ttwid}",
                "Accept": "application/json, text/plain, */*",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status_code") != 0:
        raise ValueError(
            f"抖音 API 返回错误: status_code={data.get('status_code')}, "
            f"msg={data.get('status_msg', '')}"
        )

    detail = data.get("aweme_detail")
    if not detail:
        raise ValueError("API 响应中未找到视频详情数据")

    result = _build_video_info(detail)
    _cache[aweme_id] = result
    return result


def get_cached(video_id: str) -> dict | None:
    return _cache.get(video_id)


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()


# ---------- 内部工具 ----------

def _build_video_info(detail: dict) -> dict:
    video = detail.get("video", {})
    author = detail.get("author", {})

    # 视频下载地址
    play_addr = video.get("play_addr", {})
    default_url = ""
    url_list = play_addr.get("url_list", [])
    if url_list:
        default_url = url_list[0]

    # 多清晰度
    bit_rate = video.get("bit_rate", [])
    formats = []
    for i, br in enumerate(bit_rate):
        addr = br.get("play_addr", {})
        urls = addr.get("url_list", [])
        if urls:
            w = addr.get("width", 0) or 0
            h = addr.get("height", 0) or 0
            formats.append({
                "format_id": f"douyin_{i}",
                "url": urls[0],
                "quality_type": br.get("quality_type", 0),
                "resolution": f"{w}x{h}" if w and h else "",
                "width": w,
                "height": h,
                "filesize": addr.get("data_size", 0) or 0,
                "label": _quality_label(br, w, h),
            })

    if not formats and default_url:
        w = play_addr.get("width", 0) or 0
        h = play_addr.get("height", 0) or 0
        formats.append({
            "format_id": "douyin_default",
            "url": default_url,
            "quality_type": 0,
            "resolution": f"{w}x{h}" if w and h else "",
            "width": w,
            "height": h,
            "filesize": play_addr.get("data_size", 0) or 0,
            "label": _simple_quality_label(w, h),
        })

    # 缩略图（优先使用 origin_cover，最清晰且格式兼容）
    origin_cover = video.get("origin_cover", {})
    thumbnail = (origin_cover.get("url_list", [""])[0]) if origin_cover else ""
    if not thumbnail:
        cover = video.get("cover", {})
        thumbnail = (cover.get("url_list", [""])[0]) if cover else ""
    if not thumbnail:
        dynamic_cover = video.get("dynamic_cover", {})
        thumbnail = (dynamic_cover.get("url_list", [""])[0]) if dynamic_cover else ""

    # 时长（ms -> s）
    duration_ms = video.get("duration", 0) or 0
    duration = duration_ms / 1000

    create_time = detail.get("create_time", 0) or 0
    desc = detail.get("desc", "")
    nickname = author.get("nickname", "")

    return {
        "title": desc or "抖音视频",
        "thumbnail": thumbnail,
        "duration": duration,
        "duration_string": _human_duration(duration),
        "uploader": nickname,
        "upload_date": time.strftime("%Y%m%d", time.localtime(create_time)) if create_time else "",
        "description": desc or "",
        "aweme_id": detail.get("aweme_id", ""),
        "formats": formats,
        "best_format_id": formats[0]["format_id"] if formats else None,
        "default_download_url": default_url,
    }


def _quality_label(br, w, h):
    qt = br.get("quality_type", 0)
    quality_map = {2: "标清", 13: "720P", 14: "1080P", 15: "360P", 18: "480P"}
    label = quality_map.get(qt, f"画质{qt}")
    if w and h:
        label += f" {w}x{h}"
    size = br.get("play_addr", {}).get("data_size", 0)
    if size:
        label += f" ({_human_size(size)})"
    return label


def _simple_quality_label(w, h):
    label = "默认画质"
    if w and h:
        label += f" {w}x{h}"
    return label


def _human_size(size_bytes):
    if not size_bytes:
        return "未知"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _human_duration(seconds):
    if not seconds:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
