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


def ensure_database_seeded(database_path: Path | None = None) -> bool:
    """确保数据库已建表并含有模拟数据；供应用启动时调用（云端首次部署用）。

    背景：本项目通过 .gitignore 排除了 database/*.db，云端部署拿到的是一份
    没有数据库的代码副本。若不做处理，每个页面都只会提示"数据库尚未初始化，
    请运行 python -m database.seed_data"，而 Streamlit Community Cloud 之类
    的托管环境没有可交互终端，访客无法执行该命令，整个演示等于不可用。

    行为：
        - 已有业务表且有数据 → 什么都不做，直接返回 True（幂等，多次调用安全）。
        - 否则按与命令行脚本完全相同的流程建表并写入模拟数据。
          生成过程使用固定随机种子（database.seed_data.SEED），数据内容可复现；
          时间基准相对运行当天计算，因此订单的新旧关系始终合理。

    返回:
        True 表示数据库可用（原本就有数据，或刚生成完成）；
        False 表示自动初始化失败，调用方应提示用户手动运行 seed 脚本。
    """
    path = database_path or get_config().database_path
    if is_schema_initialized(path):
        try:
            with get_connection(path) as conn:
                if _count_rows(conn, "customers") > 0:
                    return True
        except sqlite3.Error:
            return False

    # 延迟导入：seed_data 依赖 config.anomaly_rules 等模块，且会导入较重的
    # 生成逻辑；只在真正需要初始化时才加载，避免拖慢每次应用启动。
    try:
        from database import seed_data

        schema_path = Path(__file__).resolve().parent / "schema.sql"
        path.parent.mkdir(parents=True, exist_ok=True)

        conn = _connect(path)
        try:
            seed_data.apply_schema(conn, schema_path)
            conn.commit()
        finally:
            conn.close()

        gen = seed_data.SeedGenerator(seed=seed_data.SEED)
        gen.run()

        conn = _connect(path)
        try:
            seed_data.insert_all(conn, gen)
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()
        return True
    except Exception:  # noqa: BLE001 — 初始化失败不应让应用崩溃，交由调用方提示
        return False


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    """统计表内行数（表名来自内部常量，不拼接外部输入）。"""
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0]
