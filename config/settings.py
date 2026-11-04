"""
应用全局配置。

设计原则（对应技术方案 §0、§8）：
- 配置与密钥不硬编码在源代码中，统一从环境变量读取。
- 本模块只负责"读取并暴露配置"，不包含任何业务逻辑。
- 支持本地开发与云端 Demo 两种运行环境（后续部署阶段会用到 APP_ENV / DEMO_MODE，
  当前阶段先把读取骨架搭好，具体的云端隔离策略留到部署阶段再实现，避免提前
  引入未确认的复杂度）。

环境变量读取方式：优先使用标准库 os.environ，若项目根目录存在 .env 文件，
尝试做一次极简的手工解析（不引入 python-dotenv 等第三方依赖，待网络恢复、
用户确认引入该依赖后可替换为更完善的实现）。
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

# 项目根目录（本文件位于 config/ 下，上一级即项目根）
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv_if_present(env_path: Path) -> None:
    """极简 .env 解析：逐行读取 KEY=VALUE，已存在于 os.environ 的变量不覆盖。

    不处理引号转义、多行值等复杂语法；仅满足本项目当前的简单配置需求。
    待网络恢复后，如用户确认，可替换为 python-dotenv 以获得更完整的语法支持。
    """
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        # 配置文件读取失败不应阻塞应用启动；后续可接入错误处理/日志模块。
        pass


_load_dotenv_if_present(BASE_DIR / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """应用配置的只读聚合对象。"""

    # 运行环境标识：local（本地开发）/ cloud（云端 Demo）。
    # 当前阶段仅占位读取，具体行为差异在部署阶段补充。
    app_env: str

    # 应用名称，用于页面标题等展示。
    app_name: str

    # 数据库文件路径（SQLite）。阶段 1 只建立连接模块，不建业务表。
    database_path: Path

    # AI 服务模式：mock（默认）/ real。阶段 1 暂不实现 AI 服务本体，
    # 此处先占位，供后续 ai_service.py 读取。
    ai_mode: str

    # 真实大模型 API Key（可选）。阶段 1 不会被任何服务调用。
    ai_api_key: str | None

    # 是否为 Demo 模式（影响是否展示"恢复初始数据"等入口）。
    # 部署阶段补充具体行为，当前仅占位。
    demo_mode: bool


def get_config() -> AppConfig:
    """读取并返回当前应用配置。每次调用都会重新读取环境变量，
    便于测试时通过 monkeypatch 修改 os.environ 后立即生效。
    """
    database_path_raw = os.environ.get("DATABASE_PATH", "database/flowlens.db")
    database_path = Path(database_path_raw)
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path

    return AppConfig(
        app_env=os.environ.get("APP_ENV", "local"),
        app_name=os.environ.get("APP_NAME", "FlowLens AI"),
        database_path=database_path,
        ai_mode=os.environ.get("AI_MODE", "mock"),
        ai_api_key=os.environ.get("AI_API_KEY") or None,
        demo_mode=_get_bool("DEMO_MODE", False),
    )
