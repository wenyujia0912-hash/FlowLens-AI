"""
SQLite 数据库连接模块。

阶段 1 范围说明：
    本模块只负责建立和管理数据库连接，不创建任何业务表、不包含任何
    业务逻辑。业务表结构（customers、orders、anomalies 等）将在
    阶段 2（模拟数据）通过 database/schema.sql 建立。

设计要点：
    - 使用标准库 sqlite3，不引入 ORM，保持与技术方案 §1 的技术栈一致。
    - 通过 config.settings 读取数据库文件路径，不写死绝对路径。
    - 提供上下文管理器 get_connection()，确保连接在使用后正确关闭，
      避免 Streamlit 多次 rerun 导致连接泄漏。
    - 开启 foreign_keys 约束，配合技术方案 §4 的数据完整性要求。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config.settings import get_config


def ensure_database_dir(database_path: Path) -> None:
    """确保数据库文件所在目录存在。"""
    database_path.parent.mkdir(parents=True, exist_ok=True)


def _connect(database_path: Path) -> sqlite3.Connection:
    ensure_database_dir(database_path)
    conn = sqlite3.connect(
        str(database_path),
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,  # Streamlit 可能在不同回调中复用连接
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_connection(database_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """获取数据库连接的上下文管理器。

    用法：
        with get_connection() as conn:
            conn.execute(...)

    参数:
        database_path: 可选，显式指定数据库文件路径（主要用于测试时
            传入临时数据库路径）；不传则使用 config.settings 中的配置。
    """
    path = database_path or get_config().database_path
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_connection() -> bool:
    """用于启动自检：验证数据库文件可以正常连接。

    阶段 1 没有任何业务表，因此只执行一个最基础的 SQLite 内置查询
    （SELECT 1），不依赖任何业务 schema。
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute("SELECT 1;")
            return cursor.fetchone() is not None
    except sqlite3.Error:
        return False


def is_schema_initialized(database_path: Path | None = None) -> bool:
    """检查数据库是否已经建好业务表（而不只是"文件存在/能连接"）。

    【阶段7测试中发现的真实问题】sqlite3.connect() 对不存在的路径会
    自动创建一个空文件——这意味着"文件不存在"永远查不到，页面如果
    直接对 orders 等业务表做查询，会得到一个不好理解的原始报错：
    `sqlite3.OperationalError: no such table: orders`。
    这个报错确实会被 `except sqlite3.Error` 捕获、不会让应用崩溃，
    但对用户来说毫无指导意义——他们看到的是一行看不懂的SQL报错，而不是
    "请先运行 seed_data"这样明确的下一步提示（页面交互设计§5的硬性要求：
    "AI服务不可用时应显示明确提示"，这里延伸到"数据库未初始化时同样
    应给出明确提示"，是同一类问题）。

    本函数专门检测"orders 表是否存在"，页面层应该在真正查询业务数据前
    先调用这个函数，给出友好提示，而不是让原始的 OperationalError
    冒泡到用户面前。
    """
    path = database_path or get_config().database_path
    if not path.exists():
        return False
    try:
        with get_connection(path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
            ).fetchone()
            return row is not None
    except sqlite3.Error:
        return False
