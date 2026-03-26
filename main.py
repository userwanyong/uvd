"""FastAPI 入口"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import router as api_router
from api.ai_routes import router as ai_router

app = FastAPI(title="万能视频下载器", version="1.0.0")

# 注册所有 API 路由（必须在 mount 之前）
app.include_router(api_router)
app.include_router(ai_router)

# 挂载静态文件（放在路由注册之后）
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
