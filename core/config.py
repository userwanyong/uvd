"""AI 配置加载模块（零依赖）"""

import os
from pathlib import Path


def _load_env():
    """零依赖加载 .env 文件到环境变量"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


# 模块导入时自动加载 .env
_load_env()


class AIConfig:
    """AI 配置（从环境变量读取）"""

    @staticmethod
    def get_provider() -> str:
        return os.environ.get("AI_PROVIDER", "glm")

    @staticmethod
    def get_base_url() -> str:
        return os.environ.get(
            "AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
        )

    @staticmethod
    def get_api_key() -> str:
        return os.environ.get("AI_API_KEY", "")

    @staticmethod
    def get_model() -> str:
        return os.environ.get("AI_MODEL", "glm-4-flash")
