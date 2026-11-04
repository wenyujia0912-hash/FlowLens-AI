"""
运营任务业务服务。

职责边界：
    - 任务创建、状态流转、处理日志、完成校验。
    - 已完成任务必须有处理结果——在此提前拦截并抛出带清晰信息的异常，
      而不是让用户直接撞上数据库 CHECK 约束报错（技术方案 §4、§9）。
    - 任务完成不自动等同于关联异常解决——本模块创建/更新任务时**不会**
      调用 anomaly_service 去改变异常状态。两者的状态流转完全独立
      （产品需求 §5.5："任务完成不必然意味着异常自动消失"）。
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime

from models.schemas import OperationTask, TaskLog
from repositories import task_repository

VALID_STATUSES = ("待处理", "处理中", "已完成", "已取消")
VALID_PRIORITIES = ("P1", "P2", "P3")


class TaskValidationError(ValueError):
    """任务操作校验失败时抛出，调用方（未来的页面层）应捕获并展示
    友好的错误提示，而不是让异常冒泡到用户看到堆栈信息。
    """


def _new_id(prefix: str, seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefix}-{digest}"


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


def create_task(
    conn: sqlite3.Connection,
    *,
    title: str,
    assignee: str,
    due_at: str,
    priority: str = "P2",
    description: str | None = None,
    anomaly_id: str | None = None,
    order_id: str | None = None,
    now: datetime | None = None,
) -> OperationTask:
    """创建运营任务。支持从异常诊断创建（关联 anomaly_id/order_id），
    也支持手动创建一般任务（两者均可为空，产品需求 §5.5）。

    创建前必须由用户在 UI 层完成确认——本函数不做"是否已确认"的判断，
    那是调用方（页面层）的职责；本函数假定被调用时用户已经确认。
    """
    if not title or not title.strip():
        raise TaskValidationError("任务标题不能为空")
    if not assignee or not assignee.strip():
        raise TaskValidationError("必须指定负责人")
    if priority not in VALID_PRIORITIES:
        raise TaskValidationError(f"优先级不合法: {priority}，应为 {VALID_PRIORITIES}")
    if not due_at:
        raise TaskValidationError("必须指定截止时间")

    now = now or datetime.now()
    created_at = _now_iso(now)
    task_id = _new_id("TASK", f"{title}:{assignee}:{created_at}:{anomaly_id}:{order_id}")

    task = OperationTask(
        task_id=task_id,
        anomaly_id=anomaly_id,
        order_id=order_id,
        title=title.strip(),
        description=description,
        priority=priority,
        assignee=assignee.strip(),
        due_at=due_at,
        status="待处理",
        result=None,
        created_at=created_at,
        completed_at=None,
    )
    task_repository.insert(conn, task)

    _append_log(
        conn,
        task_id=task_id,
        action="创建任务",
        content=f"任务已创建，负责人：{assignee}，优先级：{priority}",
        actor=assignee,
        now=now,
    )
    return task


def update_status(
    conn: sqlite3.Connection,
    task_id: str,
    new_status: str,
    *,
    actor: str,
    result: str | None = None,
    cancel_reason: str | None = None,
    now: datetime | None = None,
) -> None:
    """更新任务状态。

    - new_status == "已完成" 时必须提供 result（产品需求 §5.5、
      页面交互设计 §3.6："完成任务时必须填写处理结果"）。
    - new_status == "已取消" 时可提供 cancel_reason（页面交互设计 §3.6：
      "取消任务时可要求填写取消原因"——原文为"可"而非"必须"，本实现
      按可选处理，待用户确认是否需要强制）。
    """
    if new_status not in VALID_STATUSES:
        raise TaskValidationError(f"任务状态不合法: {new_status}，应为 {VALID_STATUSES}")

    task = task_repository.get_by_id(conn, task_id)
    if task is None:
        raise TaskValidationError(f"任务不存在: {task_id}")

    now = now or datetime.now()
    completed_at = None

    if new_status == "已完成":
        if not result or not result.strip():
            raise TaskValidationError("完成任务必须填写处理结果")
        completed_at = _now_iso(now)
        task_repository.update_fields(
            conn, task_id, status=new_status, result=result.strip(), completed_at=completed_at
        )
        _append_log(
            conn,
            task_id=task_id,
            action="完成任务",
            content=result.strip(),
            actor=actor,
            now=now,
        )
    elif new_status == "已取消":
        task_repository.update_fields(conn, task_id, status=new_status)
        log_content = f"任务已取消" + (f"，原因：{cancel_reason}" if cancel_reason else "")
        _append_log(
            conn, task_id=task_id, action="取消任务", content=log_content, actor=actor, now=now
        )
    else:
        task_repository.update_fields(conn, task_id, status=new_status)
        _append_log(
            conn,
            task_id=task_id,
            action="更新状态",
            content=f"状态变更为：{new_status}",
            actor=actor,
            now=now,
        )


def update_assignee(
    conn: sqlite3.Connection, task_id: str, new_assignee: str, *, actor: str, now: datetime | None = None
) -> None:
    if not new_assignee or not new_assignee.strip():
        raise TaskValidationError("负责人不能为空")
    now = now or datetime.now()
    task_repository.update_fields(conn, task_id, assignee=new_assignee.strip())
    _append_log(
        conn,
        task_id=task_id,
        action="变更负责人",
        content=f"负责人变更为：{new_assignee.strip()}",
        actor=actor,
        now=now,
    )


def update_priority(
    conn: sqlite3.Connection, task_id: str, new_priority: str, *, actor: str, now: datetime | None = None
) -> None:
    if new_priority not in VALID_PRIORITIES:
        raise TaskValidationError(f"优先级不合法: {new_priority}")
    now = now or datetime.now()
    task_repository.update_fields(conn, task_id, priority=new_priority)
    _append_log(
        conn,
        task_id=task_id,
        action="调整优先级",
        content=f"优先级调整为：{new_priority}",
        actor=actor,
        now=now,
    )


def add_progress_note(
    conn: sqlite3.Connection, task_id: str, content: str, *, actor: str, now: datetime | None = None
) -> None:
    """追加处理记录（不改变任务状态，仅记录过程说明）。

    产品需求 §5.5："支持...处理记录追加"；页面交互设计 §3.6："任务日志
    采用追加式记录，避免覆盖历史处理信息。"
    """
    if not content or not content.strip():
        raise TaskValidationError("处理记录内容不能为空")
    now = now or datetime.now()
    _append_log(
        conn, task_id=task_id, action="处理记录", content=content.strip(), actor=actor, now=now
    )


def _append_log(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    action: str,
    content: str | None,
    actor: str,
    now: datetime,
) -> None:
    log_id = _new_id("LOG", f"{task_id}:{action}:{now.isoformat()}:{content}")
    log = TaskLog(
        log_id=log_id,
        task_id=task_id,
        action=action,
        content=content,
        created_at=_now_iso(now),
        actor=actor,
    )
    task_repository.insert_log(conn, log)
