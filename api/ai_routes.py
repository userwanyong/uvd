"""
AI 总结相关路由（独立 router，遵循开闭原则）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.subtitle_extractor import extract_text
from core.ai_summarizer import start_summary, get_summary_progress

router = APIRouter(prefix="/api/ai")


class SummaryRequest(BaseModel):
    url: str


@router.post("/summarize")
async def api_start_summary(req: SummaryRequest):
    """启动 AI 总结任务"""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL 不能为空")

    # 预检查：是否有可总结的文本
    sub_result = extract_text(url)
    if not sub_result.text:
        raise HTTPException(
            status_code=400,
            detail="该视频没有可用的字幕或文案内容，无法生成总结",
        )

    task_id = start_summary(url)
    return {"task_id": task_id, "status": "started"}


@router.get("/progress/{task_id}")
async def api_summary_progress(task_id: str):
    """查询总结进度"""
    task = get_summary_progress(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "video_title": task.video_title,
        "error": task.error,
    }


@router.get("/result/{task_id}")
async def api_get_result(task_id: str):
    """获取总结结果"""
    task = get_summary_progress(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == "error":
        raise HTTPException(status_code=400, detail=task.error)

    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=202, detail="总结尚未完成，请稍后再试")

    return {
        "task_id": task.task_id,
        "status": task.status,
        "video_title": task.video_title,
        "result": {
            "summary": task.result.summary,
            "outline": task.result.outline,
            "key_points": task.result.key_points,
            "mind_map": task.result.mind_map,
        },
    }
