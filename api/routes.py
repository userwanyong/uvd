"""API 路由"""

import os
import asyncio
import base64
import httpx

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from core.downloader import (
    VideoInfo,
    DownloadProgress,
    extract_info,
    download_video,
    get_progress,
    get_download_file,
)

router = APIRouter(prefix="/api")


class InfoRequest(BaseModel):
    url: str


class ThumbnailRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str | None = None


@router.post("/info")
async def api_extract_info(req: InfoRequest):
    """解析视频URL，返回视频信息和可用格式"""
    try:
        # extract_info 是阻塞调用，放到线程中避免阻塞事件循环
        info = await asyncio.to_thread(extract_info, req.url)
        # 缩略图直链 base64 编码后传给前端，前端通过代理获取
        thumbnail_url = ""
        if info.thumbnail:
            encoded = base64.urlsafe_b64encode(info.thumbnail.encode()).decode().rstrip("=")
            thumbnail_url = f"/api/proxy-thumbnail/{encoded}"
        return {
            "title": info.title,
            "thumbnail": thumbnail_url,
            "duration": info.duration,
            "duration_string": info.duration_string,
            "uploader": info.uploader,
            "upload_date": info.upload_date,
            "description": info.description,
            "best_format_id": info.best_format_id,
            "formats": [
                {
                    "format_id": f.format_id,
                    "label": f.label,
                    "resolution": f.resolution,
                    "ext": f.ext,
                    "vcodec": f.vcodec,
                    "acodec": f.acodec,
                }
                for f in info.formats
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")


@router.get("/proxy-thumbnail/{encoded_url}")
async def proxy_thumbnail(encoded_url: str):
    """代理获取缩略图，绕过跨域和防盗链限制"""
    try:
        # base64 解码还原缩略图原始 URL
        padding = 4 - len(encoded_url) % 4
        if padding != 4:
            encoded_url += "=" * padding
        url = base64.urlsafe_b64decode(encoded_url).decode()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        # 抖音 CDN 需要固定 Referer
        if "douyinpic.com" in url or "douyinvod.com" in url:
            headers["Referer"] = "https://www.douyin.com/"
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10,
            headers=headers,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail="缩略图获取失败")


@router.post("/download")
async def api_download(req: DownloadRequest):
    """开始下载视频，返回 task_id"""
    try:
        task_id = download_video(req.url, req.format_id)
        return {"task_id": task_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载启动失败: {str(e)}")


@router.get("/progress/{task_id}")
async def api_progress(task_id: str):
    """查询下载进度"""
    progress = get_progress(task_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": progress.task_id,
        "status": progress.status,
        "progress": round(progress.progress, 1),
        "speed": round(progress.speed or 0, 1),
        "downloaded_bytes": progress.downloaded_bytes,
        "total_bytes": progress.total_bytes,
        "error": progress.error,
    }


@router.get("/file/{task_id}")
async def api_get_file(task_id: str):
    """下载完成的文件"""
    filepath = get_download_file(task_id)
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在或下载未完成")
    filename = os.path.basename(filepath)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )
