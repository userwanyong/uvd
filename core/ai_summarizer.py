"""
AI 总结引擎 —— 管理总结任务生命周期，调用 OpenAI 兼容 API 生成结构化总结。

使用 openai SDK 统一对接 GLM / DeepSeek / OpenAI 等后端。
"""

import re
import uuid
import logging
import threading
from dataclasses import dataclass, field

from openai import OpenAI

from core.config import AIConfig
from core.subtitle_extractor import extract_text

logger = logging.getLogger(__name__)

# ─── 数据类 ─────────────────────────────────────────────


@dataclass
class SummaryResult:
    """AI 总结结果"""

    summary: str = ""  # 智能总结
    outline: str = ""  # 章节大纲（Markdown）
    key_points: str = ""  # 核心要点（Markdown）
    mind_map: str = ""  # 思维导图（Markdown 嵌套列表）


@dataclass
class SummaryTask:
    """总结任务状态"""

    task_id: str
    status: str = "pending"  # pending / extracting / summarizing / completed / error
    progress: str = ""  # 人类可读的进度描述
    video_title: str = ""
    result: SummaryResult | None = None
    error: str = ""


# 内存中保存总结任务状态（与 downloader.py 模式一致）
_tasks: dict[str, SummaryTask] = {}

# ─── System Prompt ──────────────────────────────────────

SYSTEM_PROMPT = """你是一个专业的视频内容分析助手。用户会提供视频的字幕文本或文案内容，请根据内容生成以下四个部分。

## 输出格式要求（严格按以下格式输出，每个部分用 ### 开头）

### 智能总结
用 3-5 句话概括视频的核心内容，让读者快速了解视频讲了什么。

### 章节大纲
按照视频内容的逻辑顺序，列出主要章节。每个章节用二级标题（##），章节下的要点用无序列表（- 开头）。

### 核心要点
提取 5-8 个最关键的知识点或观点，每个要点用 **加粗标题** + 简短说明的形式呈现。

### 思维导图
用 Markdown 嵌套列表的形式呈现内容的层级结构。从核心主题展开，用缩进表示层级关系。格式示例：
- 核心主题
  - 分支一
    - 子要点1
    - 子要点2
  - 分支二
    - 子要点1

请确保：
- 内容准确，忠于原始文本
- 语言简洁，结构清晰
- 适合学习和复习
- 如果文本内容过短（如少于50字），请基于现有内容尽量总结"""


# ─── 公开接口 ───────────────────────────────────────────


def start_summary(url: str) -> str:
    """
    启动总结任务（后台线程），返回 task_id。
    """
    task_id = uuid.uuid4().hex[:8]
    task = SummaryTask(task_id=task_id, status="pending", progress="准备中...")
    _tasks[task_id] = task

    thread = threading.Thread(target=_do_summary, args=(task, url), daemon=True)
    thread.start()

    return task_id


def get_summary_progress(task_id: str) -> SummaryTask | None:
    """查询总结任务状态"""
    return _tasks.get(task_id)


# ─── 内部实现 ───────────────────────────────────────────


def _get_ai_client() -> OpenAI:
    """创建 OpenAI 兼容客户端"""
    return OpenAI(
        base_url=AIConfig.get_base_url(),
        api_key=AIConfig.get_api_key(),
    )


def _do_summary(task: SummaryTask, url: str):
    """后台线程执行的总结逻辑"""
    try:
        # 1. 提取文本
        task.status = "extracting"
        task.progress = "正在提取字幕文本..."
        logger.info("[%s] 开始提取文本: %s", task.task_id, url)

        sub_result = extract_text(url)

        if not sub_result.text:
            task.status = "error"
            task.error = "该视频没有可用的字幕或文案内容，无法生成总结"
            task.progress = "提取失败"
            logger.warning("[%s] 无可用文本: %s", task.task_id, url)
            return

        # 截断过长的文本（避免超出模型上下文限制）
        text = sub_result.text[:12000]
        text_source = "字幕" if sub_result.source == "subtitle" else "视频文案"
        logger.info(
            "[%s] 文本提取成功: source=%s, len=%d",
            task.task_id,
            sub_result.source,
            len(text),
        )

        # 2. 获取视频标题
        task.video_title = _extract_title(url, text)
        task.progress = f"已提取{text_source}（{len(text)} 字），正在 AI 总结..."

        # 3. 调用 AI
        task.status = "summarizing"
        logger.info("[%s] 开始 AI 总结...", task.task_id)

        client = _get_ai_client()
        response = client.chat.completions.create(
            model=AIConfig.get_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"视频标题：{task.video_title}\n\n视频内容文本：\n{text}",
                },
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        raw = response.choices[0].message.content
        logger.info("[%s] AI 返回 %d 字符", task.task_id, len(raw) if raw else 0)

        # 4. 解析结果
        task.result = _parse_result(raw)
        task.status = "completed"
        task.progress = "总结完成"
        logger.info("[%s] 总结完成", task.task_id)

    except Exception as e:
        task.status = "error"
        task.error = str(e)
        task.progress = "总结失败"
        logger.error("[%s] 总结失败: %s", task.task_id, e, exc_info=True)


def _extract_title(url: str, text: str) -> str:
    """尝试获取视频标题，失败时用文本第一行"""
    try:
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 10,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return (info.get("title") or "").strip()
    except Exception:
        # 用文本第一行作为标题
        first_line = text.split("\n")[0].strip()
        return first_line[:80] if first_line else "未知视频"


def _parse_result(raw: str) -> SummaryResult:
    """将 AI 返回的 Markdown 拆分为四个部分"""
    result = SummaryResult()

    if not raw:
        return result

    # 按 ### 标题拆分
    parts = re.split(r"\n*###\s+", raw)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 判断属于哪个部分
        if part.startswith("智能总结") or part.startswith("总结"):
            result.summary = re.sub(r"^智能总结\s*\n*", "", part).strip()
        elif part.startswith("章节大纲") or part.startswith("大纲"):
            result.outline = re.sub(r"^章节大纲\s*\n*", "", part).strip()
        elif part.startswith("核心要点") or part.startswith("要点"):
            result.key_points = re.sub(r"^核心要点\s*\n*", "", part).strip()
        elif part.startswith("思维导图") or part.startswith("导图"):
            result.mind_map = re.sub(r"^思维导图\s*\n*", "", part).strip()

    # 如果拆分失败（AI 没有按格式输出），把全部内容放到 summary
    if not result.summary and not result.outline:
        result.summary = raw.strip()

    return result
