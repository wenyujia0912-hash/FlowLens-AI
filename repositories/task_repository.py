"""
运营任务与任务日志数据访问层。

职责边界：仅做 SQL 读写。"已完成任务是否必须有结果"之类的业务规则校验
在 service 层提前拦截（给出友好错误信息），数据库 CHECK 约束作为最后一道
防线（即使跳过 service 层直接写库也不会产生违反约束的数据）。
"""

from __future__ import annotations

import sqlite3

from models.schemas import OperationTask, TaskLog


def _row_to_task(row: sqlite3.Row) -> OperationTask:
    return OperationTask(
        task_id=row["task_id"],
        anomaly_id=row["anomaly_id"],
        order_id=row["order_id"],
        title=row["title"],
        description=row["description"],
        priority=row["priority"],
        assignee=row["assignee"],
        due_at=row["due_at"],
        status=row["status"],
        result=row["result"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


def get_by_id(conn: sqlite3.Connection, task_id: str) -> OperationTask | None:
    row = conn.execute(
        "SELECT * FROM operation_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    return _row_to_task(row) if row else None


def list_all(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_before: str | None = None,
    order_by: str = "due_at",
) -> list[OperationTask]:
    """列出任务，支持按状态/优先级/负责人/截止时间筛选和排序
    （产品需求 §5.5；页面交互设计 §3.6）。
    """
    allowed_order_by = {"due_at", "created_at", "priority"}
    if order_by not in allowed_order_by:
        order_by = "due_at"

    clauses: list[str] = []
    params: list[str] = []

    if status:
        clauses.append("status = ?")
        params.append(status)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if assignee:
        clauses.append("assignee = ?")
        params.append(assignee)
    if due_before:
        clauses.append("due_at <= ?")
        params.append(due_before)

    sql = "SELECT * FROM operation_tasks"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {order_by} ASC"

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_task(r) for r in rows]


def list_overdue(conn: sqlite3.Connection, now_iso: str) -> list[OperationTask]:
    """逾期任务：due_at 已过且状态非"已完成"/"已取消"。

    这是阶段 0 产出的 H1 歧义问题的实现——文档未明确定义"逾期任务"口径，
    此为本阶段采用的默认假设，待用户确认。
    """
    rows = conn.execute(
        """SELECT * FROM operation_tasks
           WHERE due_at < ? AND status NOT IN ('已完成', '已取消')
           ORDER BY due_at ASC""",
        (now_iso,),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def list_by_anomaly(conn: sqlite3.Connection, anomaly_id: str) -> list[OperationTask]:
    rows = conn.execute(
        "SELECT * FROM operation_tasks WHERE anomaly_id = ? ORDER BY created_at DESC",
        (anomaly_id,),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def list_by_order(conn: sqlite3.Connection, order_id: str) -> list[OperationTask]:
    rows = conn.execute(
        "SELECT * FROM operation_tasks WHERE order_id = ? ORDER BY created_at DESC",
        (order_id,),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def insert(conn: sqlite3.Connection, task: OperationTask) -> None:
    conn.execute(
        """INSERT INTO operation_tasks
           (task_id, anomaly_id, order_id, title, description, priority, assignee,
            due_at, status, result, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task.task_id,
            task.anomaly_id,
            task.order_id,
            task.title,
            task.description,
            task.priority,
            task.assignee,
            task.due_at,
            task.status,
            task.result,
            task.created_at,
            task.completed_at,
        ),
    )


def update_fields(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    status: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    due_at: str | None = None,
    result: str | None = None,
    completed_at: str | None = None,
) -> None:
    """按需更新任务字段。只更新显式传入（非 None）的字段。

    注意：result/completed_at 传 None 不代表"清空"，而是"不修改"——
    如需显式清空，应由调用方使用专门的方法（当前阶段未实现该需求）。
    """
    sets: list[str] = []
    params: list[str] = []

    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if assignee is not None:
        sets.append("assignee = ?")
        params.append(assignee)
    if priority is not None:
        sets.append("priority = ?")
        params.append(priority)
    if due_at is not None:
        sets.append("due_at = ?")
        params.append(due_at)
    if result is not None:
        sets.append("result = ?")
        params.append(result)
    if completed_at is not None:
        sets.append("completed_at = ?")
        params.append(completed_at)

    if not sets:
        return

    params.append(task_id)
    conn.execute(
        f"UPDATE operation_tasks SET {', '.join(sets)} WHERE task_id = ?", params
    )


# --- 任务日志（追加式，不覆盖历史） ---


def _row_to_log(row: sqlite3.Row) -> TaskLog:
    return TaskLog(
        log_id=row["log_id"],
        task_id=row["task_id"],
        action=row["action"],
        content=row["content"],
        created_at=row["created_at"],
        actor=row["actor"],
    )


def insert_log(conn: sqlite3.Connection, log: TaskLog) -> None:
    conn.execute(
        """INSERT INTO task_logs (log_id, task_id, action, content, created_at, actor)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (log.log_id, log.task_id, log.action, log.content, log.created_at, log.actor),
    )


def list_logs_for_task(conn: sqlite3.Connection, task_id: str) -> list[TaskLog]:
    """按时间正序返回任务的全部日志，用于时间线展示
    （页面交互设计 §3.6："处理记录时间线"）。
    """
    rows = conn.execute(
        "SELECT * FROM task_logs WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    return [_row_to_log(r) for r in rows]
