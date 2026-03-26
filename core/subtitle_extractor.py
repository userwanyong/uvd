"""
字幕提取引擎 —— 从视频 URL 中提取可用于 AI 总结的纯文本内容。

抖音：通过 API 获取视频文案（desc）
其他平台：通过 yt-dlp 获取字幕（subtitles / automatic_captions），无字幕时 fallback 到 description
"""

import re
import logging
from dataclasses import dataclass

import httpx
import yt_dlp

from core.douyin_parser import parse as douyin_parse

logger = logging.getLogger(__name__)

# 字幕语言优先级
_LANG_PRIORITY = ["zh-Hans", "zh", "zh-CN", "zh-TW", "zh-Hant", "en", "en-US", "en-GB"]

# yt-dlp 提取字幕时的配置（与 downloader.py 保持风格一致）
_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 15,
    "retries": 2,
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    },
}


@dataclass
class SubtitleResult:
    """字幕提取结果"""

    text: str  # 提取到的纯文本
    source: str  # "subtitle" | "description" | "none"
    lang: str  # 检测到的语言代码
    has_subtitles: bool  # 是否有字幕
    available_langs: list[str]  # 可用字幕语言列表


def extract_text(url: str) -> SubtitleResult:
    """
    从视频 URL 提取文本内容。

    抖音走 desc 文案，其他平台走 yt-dlp 字幕。
    """
    if _is_douyin_url(url):
        return _extract_douyin_text(url)
    return _extract_ytdlp_text(url)


def _is_douyin_url(url: str) -> bool:
    return bool(re.match(r"https?://(?:www\.)?douyin\.com/", url))


# ─── 抖音路径 ───────────────────────────────────────────


def _extract_douyin_text(url: str) -> SubtitleResult:
    """从抖音视频提取文案"""
    try:
        info = douyin_parse(url)
        desc = info.get("description", "") or ""
        if desc and len(desc.strip()) >= 10:
            return SubtitleResult(
                text=desc.strip(),
                source="description",
                lang="zh",
                has_subtitles=False,
                available_langs=[],
            )
        return SubtitleResult(
            text="",
            source="none",
            lang="unknown",
            has_subtitles=False,
            available_langs=[],
        )
    except Exception as e:
        logger.error("抖音文案提取失败: %s", e)
        return SubtitleResult(
            text="",
            source="none",
            lang="unknown",
            has_subtitles=False,
            available_langs=[],
        )


# ─── yt-dlp 路径 ──────────────────────────────────────


def _extract_ytdlp_text(url: str) -> SubtitleResult:
    """从 yt-dlp 提取字幕或 description"""
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error("yt-dlp 提取视频信息失败: %s", e)
        return SubtitleResult(
            text="",
            source="none",
            lang="unknown",
            has_subtitles=False,
            available_langs=[],
        )

    subtitles = info.get("subtitles", {})
    auto_captions = info.get("automatic_captions", {})

    # 收集所有可用语言
    all_langs = list(subtitles.keys()) + [
        lang for lang in auto_captions if lang not in subtitles
    ]

    # 按优先级查找可用字幕
    for lang in _LANG_PRIORITY:
        # 手动字幕优先
        if lang in subtitles:
            text = _download_subtitle(subtitles[lang])
            if text:
                return SubtitleResult(
                    text=text,
                    source="subtitle",
                    lang=lang,
                    has_subtitles=True,
                    available_langs=all_langs,
                )
        # 自动生成字幕
        if lang in auto_captions:
            text = _download_subtitle(auto_captions[lang])
            if text:
                return SubtitleResult(
                    text=text,
                    source="subtitle",
                    lang=lang,
                    has_subtitles=True,
                    available_langs=all_langs,
                )

    # 没有字幕，fallback 到 description
    description = (info.get("description") or "").strip()
    if len(description) >= 10:
        return SubtitleResult(
            text=description,
            source="description",
            lang="unknown",
            has_subtitles=False,
            available_langs=all_langs,
        )

    return SubtitleResult(
        text="",
        source="none",
        lang="unknown",
        has_subtitles=False,
        available_langs=all_langs,
    )


def _download_subtitle(formats: list[dict]) -> str:
    """从字幕格式列表中下载并解析字幕文本"""
    if not formats:
        return ""

    # 选择最佳格式（优先 vtt，其次 srt）
    chosen = None
    for ext in ("vtt", "srt", "srv3", "srv2", "srv1", "ttml", "json3"):
        matches = [f for f in formats if f.get("ext") == ext]
        if matches:
            chosen = matches[-1]
            break
    if not chosen:
        chosen = formats[-1]

    url = chosen.get("url")
    if not url:
        return ""

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        content = resp.text
        text = _subtitle_to_text(content)
        return text if len(text.strip()) >= 10 else ""
    except Exception as e:
        logger.warning("字幕下载失败: %s", e)
        return ""


def _subtitle_to_text(content: str) -> str:
    """将 VTT/SRT/其他字幕格式转换为纯文本"""
    # 移除 VTT 头部
    text = re.sub(r"WEBVTT.*?\n\n", "", content, flags=re.DOTALL)
    # 移除 TTML 头部
    text = re.sub(r"<\?xml.*?\?>", "", text, flags=re.DOTALL)
    text = re.sub(r"<tt\b.*?</tt>", "", text, flags=re.DOTALL)
    # 移除时间戳行（VTT 格式）
    text = re.sub(
        r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}",
        "",
        text,
    )
    # 移除时间戳行（SRT 格式，含逗号毫秒）
    text = re.sub(
        r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}",
        "",
        text,
    )
    # 移除序号行（SRT 格式）
    text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
    # 移除位置/样式标记
    text = re.sub(r"(align|position|line|size|color):[^\n<]*", "", text)
    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 移除 { } 花括号内容（YouTube 内部格式）
    text = re.sub(r"\{[^}]*\}", "", text)
    # 移除多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
